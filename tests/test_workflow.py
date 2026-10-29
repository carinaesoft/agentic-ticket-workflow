"""TicketWorkflow in the time-skipping test server, with fake activities registered under
the real activity names."""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import timedelta
from decimal import Decimal
from typing import Any

from temporalio import activity
from temporalio.client import WorkflowHandle
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from app.activities import ActionRequest, DecideOutput
from app.data.store import DataStore
from app.domain.models import (
    ActionResult,
    ApprovalInput,
    DecisionContext,
    EscalateAction,
    ProposedDecision,
    RefundAction,
    ReplyAction,
    Ticket,
    WorkflowStatus,
    WorkflowStep,
)
from app.workflows.ticket import TicketWorkflow

STORE = DataStore()

REPLY = {"kind": "reply", "message": "Use the reset link.", "article_ids": ["KB-1"]}
REFUND = {"kind": "refund", "invoice_id": "INV-1002", "amount_eur": "49.00"}


def ticket(customer_id: str = "C-101") -> Ticket:
    return Ticket(
        ticket_id=f"T-{uuid.uuid4().hex[:8]}",
        customer_id=customer_id,
        subject="subject",
        body="body",
    )


def decide_output(action: dict[str, Any], customer_id: str = "C-101", **decision) -> DecideOutput:
    return DecideOutput(
        decision=ProposedDecision.model_validate(
            {"category": "billing", "priority": "high", "action": action, **decision}
        ),
        context=DecisionContext(
            customer=STORE.get_customer(customer_id),
            invoices=STORE.invoices_for(customer_id),
            kb_ids=STORE.kb_ids(),
        ),
    )


class FakeActivities:
    """Scriptable stand-ins for decide_ticket / execute_action / lookup_action_result.

    ``lose_responses`` makes every successful attempt apply the action once (keyed like the
    Helpdesk) and then fail as if the response was lost.
    """

    def __init__(
        self,
        decide: DecideOutput | None = None,
        decide_error: Exception | None = None,
        act_failures: int = 0,
        act_gate: asyncio.Event | None = None,
        lose_responses: bool = False,
    ) -> None:
        self.decide = decide
        self.decide_error = decide_error
        self.act_failures = act_failures
        self.act_gate = act_gate
        self.lose_responses = lose_responses
        self.decide_attempts = 0
        self.act_attempts: list[int] = []
        self.executed: list[ActionRequest] = []
        self.recorded: dict[str, ActionResult] = {}
        self.lookups: list[str] = []

    def as_list(self) -> list:
        @activity.defn(name="decide_ticket")
        async def decide_ticket(ticket: Ticket) -> DecideOutput:
            self.decide_attempts += 1
            if self.decide_error is not None:
                raise self.decide_error
            return self.decide

        @activity.defn(name="execute_action")
        async def execute_action(request: ActionRequest) -> ActionResult:
            attempt = activity.info().attempt
            self.act_attempts.append(attempt)
            if self.act_gate is not None:
                await self.act_gate.wait()
            if attempt <= self.act_failures:
                raise ApplicationError("helpdesk down", type="HelpdeskTransientError")
            key = f"{request.workflow_id}:{request.action.kind}"
            if key not in self.recorded:
                self.executed.append(request)
                self.recorded[key] = ActionResult(
                    kind=request.action.kind,
                    helpdesk_reference="HD-1",
                    idempotency_key=key,
                    outcome_message="done",
                )
            if self.lose_responses:
                raise ApplicationError(
                    "helpdesk response lost after the action was applied",
                    type="HelpdeskTransientError",
                )
            return self.recorded[key]

        @activity.defn(name="lookup_action_result")
        async def lookup_action_result(request: ActionRequest) -> ActionResult | None:
            key = f"{request.workflow_id}:{request.action.kind}"
            self.lookups.append(key)
            return self.recorded.get(key)

        return [decide_ticket, execute_action, lookup_action_result]


@asynccontextmanager
async def started(env: WorkflowEnvironment, fake: FakeActivities, t: Ticket | None = None):
    t = t or ticket()
    task_queue = f"tq-{uuid.uuid4()}"
    async with Worker(
        env.client, task_queue=task_queue, workflows=[TicketWorkflow], activities=fake.as_list()
    ):
        handle = await env.client.start_workflow(
            TicketWorkflow.run, t, id=f"ticket-{t.ticket_id}", task_queue=task_queue
        )
        yield handle


async def wait_for_step(handle: WorkflowHandle, step: WorkflowStep) -> WorkflowStatus:
    for _ in range(200):
        status = await handle.query(TicketWorkflow.status)
        if status.step == step:
            return status
        await asyncio.sleep(0.05)
    raise AssertionError(f"workflow never reached {step}, last: {status.step}")


async def result(handle: WorkflowHandle) -> WorkflowStatus:
    return await handle.result()


async def test_answered_ticket_completes_with_reply(env) -> None:
    fake = FakeActivities(decide=decide_output(REPLY, category="account", priority="normal"))
    async with started(env, fake) as handle:
        status = await result(handle)
        # The status stays readable after the workflow has finished (a worker is needed).
        assert await handle.query(TicketWorkflow.status) == status

    assert status.step == WorkflowStep.COMPLETED
    assert status.decision.action == ReplyAction(**REPLY)
    assert status.result.kind == "reply"
    assert [r.action.kind for r in fake.executed] == ["reply"]
    assert status.workflow_id == handle.id
    assert status.updated_at is not None


async def test_refund_approved_waits_then_refunds_once(env) -> None:
    fake = FakeActivities(decide=decide_output(REFUND))
    async with started(env, fake) as handle:
        waiting = await wait_for_step(handle, WorkflowStep.AWAITING_APPROVAL)
        assert waiting.decision.action == RefundAction(
            invoice_id="INV-1002", amount_eur=Decimal("49.00")
        )
        assert fake.executed == []
        await handle.signal(
            TicketWorkflow.submit_approval, ApprovalInput(approved=True, reviewer="lead")
        )
        status = await result(handle)

    assert status.step == WorkflowStep.COMPLETED
    assert status.approval.reviewer == "lead"
    assert [r.action.kind for r in fake.executed] == ["refund"]


async def test_refund_without_answer_escalates_after_24_hours(env) -> None:
    fake = FakeActivities(decide=decide_output(REFUND))
    async with started(env, fake) as handle:
        waiting = await wait_for_step(handle, WorkflowStep.AWAITING_APPROVAL)
        await env.sleep(timedelta(hours=23, minutes=59))
        still = await handle.query(TicketWorkflow.status)
        assert still.step == WorkflowStep.AWAITING_APPROVAL  # one minute before the deadline
        assert fake.executed == []
        status = await result(handle)  # the test server skips the rest of the 24 h timer

    assert status.updated_at - waiting.updated_at >= timedelta(hours=24)
    assert status.step == WorkflowStep.COMPLETED
    assert status.decision.action == EscalateAction(
        reason="refund approval not received within 24 hours"
    )
    assert [r.action.kind for r in fake.executed] == ["escalate"]


async def test_refund_rejected_becomes_reply(env) -> None:
    fake = FakeActivities(decide=decide_output(REFUND))
    async with started(env, fake) as handle:
        await wait_for_step(handle, WorkflowStep.AWAITING_APPROVAL)
        await handle.signal(
            TicketWorkflow.submit_approval,
            ApprovalInput(approved=False, reviewer="lead", comment="Charge was correct."),
        )
        status = await result(handle)

    action = status.decision.action
    assert isinstance(action, ReplyAction)
    assert action.article_ids == ["KB-2"]
    assert "not approved" in action.message
    assert "Charge was correct." in action.message
    assert [r.action.kind for r in fake.executed] == ["reply"]


async def test_execute_action_fails_twice_then_succeeds(env) -> None:
    fake = FakeActivities(decide=decide_output(REPLY), act_failures=2)
    async with started(env, fake) as handle:
        status = await result(handle)

    assert status.step == WorkflowStep.COMPLETED
    assert fake.act_attempts == [1, 2, 3]
    assert len(fake.executed) == 1


async def test_rule_violating_decision_escalates_with_reason(env) -> None:
    over_limit = {**REFUND, "invoice_id": "INV-1001", "amount_eur": "5000.00"}
    fake = FakeActivities(decide=decide_output(over_limit))
    async with started(env, fake) as handle:
        status = await result(handle)

    assert status.step == WorkflowStep.COMPLETED
    assert status.proposed_decision.action.kind == "refund"
    assert status.validation_errors == [
        "refund amount 5000.00 exceeds invoice INV-1001 amount 49.00"
    ]
    assert status.decision.action == EscalateAction(
        reason="decision rejected by rules: refund amount 5000.00 exceeds invoice INV-1001 "
        "amount 49.00"
    )
    assert [r.action.kind for r in fake.executed] == ["escalate"]


async def test_unknown_customer_escalates_with_reason(env) -> None:
    error = ApplicationError("unknown customer C-999", type="UnknownCustomer", non_retryable=True)
    fake = FakeActivities(decide_error=error)
    async with started(env, fake, ticket("C-999")) as handle:
        status = await result(handle)

    assert fake.decide_attempts == 1
    assert status.step == WorkflowStep.COMPLETED
    assert status.proposed_decision is None
    assert status.decision.action == EscalateAction(reason="unknown customer C-999")
    assert (status.decision.category, status.decision.priority) == ("other", "normal")


async def test_decide_retries_exhausted_escalates(env) -> None:
    fake = FakeActivities(decide_error=ApplicationError("rate limited", type="RateLimitError"))
    async with started(env, fake) as handle:
        status = await result(handle)

    assert fake.decide_attempts == 3
    assert status.decision.action == EscalateAction(
        reason="decision step failed after 3 attempts: RateLimitError"
    )


async def test_act_always_failing_ends_failed_with_reason(env) -> None:
    fake = FakeActivities(decide=decide_output(REPLY), act_failures=99)
    async with started(env, fake) as handle:
        status = await result(handle)
        assert (await handle.query(TicketWorkflow.status)).step == WorkflowStep.FAILED

    assert status.step == WorkflowStep.FAILED
    assert status.result is None
    assert status.failure_reason == "helpdesk unavailable after 5 attempts: HelpdeskTransientError"
    assert fake.act_attempts == [1, 2, 3, 4, 5]
    assert fake.lookups == [f"{handle.id}:reply"]  # reconciled once, nothing was recorded
    assert fake.executed == []


async def test_action_applied_but_every_response_lost_reconciles_to_completed(env) -> None:
    fake = FakeActivities(decide=decide_output(REPLY), lose_responses=True)
    async with started(env, fake) as handle:
        status = await result(handle)

    assert fake.act_attempts == [1, 2, 3, 4, 5]
    assert fake.lookups == [f"{handle.id}:reply"]
    assert status.step == WorkflowStep.COMPLETED
    assert status.failure_reason is None
    assert status.result == fake.recorded[f"{handle.id}:reply"]
    assert len(fake.executed) == 1  # exactly one effect


async def test_refund_applied_only_in_last_attempt_reconciles_to_completed(env) -> None:
    fake = FakeActivities(decide=decide_output(REFUND), act_failures=4, lose_responses=True)
    async with started(env, fake) as handle:
        await wait_for_step(handle, WorkflowStep.AWAITING_APPROVAL)
        await handle.signal(
            TicketWorkflow.submit_approval, ApprovalInput(approved=True, reviewer="lead")
        )
        status = await result(handle)

    assert fake.act_attempts == [1, 2, 3, 4, 5]
    assert status.step == WorkflowStep.COMPLETED
    assert status.result.idempotency_key == f"{handle.id}:refund"
    assert [r.action.kind for r in fake.executed] == ["refund"]


async def test_approval_after_timeout_is_ignored(env) -> None:
    gate = asyncio.Event()
    fake = FakeActivities(decide=decide_output(REFUND), act_gate=gate)
    async with started(env, fake) as handle:
        await wait_for_step(handle, WorkflowStep.AWAITING_APPROVAL)
        # Waiting for the result lets the test server skip the 24 h timer; the gated act
        # activity then holds the workflow in ``acting`` while the late approval arrives.
        pending = asyncio.create_task(result(handle))
        await wait_for_step(handle, WorkflowStep.ACTING)
        await handle.signal(
            TicketWorkflow.submit_approval, ApprovalInput(approved=True, reviewer="late")
        )
        gate.set()
        status = await pending

    assert status.approval is None
    assert status.decision.action == EscalateAction(
        reason="refund approval not received within 24 hours"
    )
    assert [r.action.kind for r in fake.executed] == ["escalate"]


async def test_second_approval_is_ignored(env) -> None:
    gate = asyncio.Event()
    fake = FakeActivities(decide=decide_output(REFUND), act_gate=gate)
    async with started(env, fake) as handle:
        await wait_for_step(handle, WorkflowStep.AWAITING_APPROVAL)
        await handle.signal(
            TicketWorkflow.submit_approval, ApprovalInput(approved=False, reviewer="first")
        )
        await wait_for_step(handle, WorkflowStep.ACTING)
        await handle.signal(
            TicketWorkflow.submit_approval, ApprovalInput(approved=True, reviewer="second")
        )
        gate.set()
        status = await result(handle)

    assert status.approval.reviewer == "first"
    assert [r.action.kind for r in fake.executed] == ["reply"]
