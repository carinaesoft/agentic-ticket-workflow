"""The ticket workflow: decide -> validate -> (await approval, refunds only) -> act.

The workflow is the only orchestrator. Everything non-deterministic happens in the two
activities; the business rules run here, inline, on every decision, so nothing an activity
returns can skip them. Timeouts and retry policies are module constants (never read from
the environment) so a configuration change cannot break replay.
"""

from __future__ import annotations

import contextlib
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError, RetryState
from temporalio.exceptions import TimeoutError as ActivityTimeoutError

with workflow.unsafe.imports_passed_through():
    from app.activities import ActionRequest, DecideOutput
    from app.domain.models import (
        ActionResult,
        ApprovalInput,
        Category,
        Decision,
        EscalateAction,
        Priority,
        RefundAction,
        ReplyAction,
        Ticket,
        WorkflowStatus,
        WorkflowStep,
    )
    from app.domain.rules import validate_decision

APPROVAL_TIMEOUT = timedelta(hours=24)
DECIDE_TIMEOUT = timedelta(seconds=180)
ACT_TIMEOUT = timedelta(seconds=10)
DECIDE_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=10),
    maximum_attempts=3,
)
ACT_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=10),
    maximum_attempts=5,
)
APPROVAL_TIMEOUT_REASON = "refund approval not received within 24 hours"
REFUND_POLICY_ARTICLE = "KB-2"


@workflow.defn
class TicketWorkflow:
    @workflow.init
    def __init__(self, ticket: Ticket) -> None:
        self._ticket = ticket
        self._approval: ApprovalInput | None = None
        self._status = WorkflowStatus(
            ticket_id=ticket.ticket_id, workflow_id=workflow.info().workflow_id
        )

    @workflow.run
    async def run(self, ticket: Ticket) -> WorkflowStatus:
        self._set_step(WorkflowStep.DECIDING)
        try:
            out = await workflow.execute_activity(
                "decide_ticket",
                ticket,
                result_type=DecideOutput,
                start_to_close_timeout=DECIDE_TIMEOUT,
                retry_policy=DECIDE_RETRY,
            )
        except ActivityError as err:
            reason = _failure_reason(err, f"decision step failed after {_attempts(DECIDE_RETRY)}")
            decision = Decision(
                category=Category.OTHER,
                priority=Priority.NORMAL,
                action=EscalateAction(reason=reason),
            )
            self._log("decision_failed", reason=reason)
        else:
            self._status.proposed_decision = out.decision
            self._set_step(WorkflowStep.VALIDATING)
            outcome = validate_decision(out.decision, ticket, out.context)
            self._status.validation_errors = outcome.errors
            decision = outcome.decision
            if outcome.errors:
                self._log("decision_rejected_by_rules", errors=outcome.errors)
        self._status.decision = decision

        if isinstance(decision.action, RefundAction):
            decision = await self._await_approval(decision)
            self._status.decision = decision

        self._set_step(WorkflowStep.ACTING)
        try:
            result = await workflow.execute_activity(
                "execute_action",
                ActionRequest(
                    workflow_id=self._status.workflow_id,
                    ticket_id=ticket.ticket_id,
                    action=decision.action,
                ),
                result_type=ActionResult,
                start_to_close_timeout=ACT_TIMEOUT,
                retry_policy=ACT_RETRY,
            )
        except ActivityError as err:
            self._status.failure_reason = _failure_reason(
                err, f"helpdesk unavailable after {_attempts(ACT_RETRY)}"
            )
            self._set_step(WorkflowStep.FAILED)
        else:
            self._status.result = result
            self._set_step(WorkflowStep.COMPLETED)
        return self._status

    async def _await_approval(self, decision: Decision) -> Decision:
        self._set_step(WorkflowStep.AWAITING_APPROVAL)
        with contextlib.suppress(TimeoutError):
            await workflow.wait_condition(
                lambda: self._approval is not None, timeout=APPROVAL_TIMEOUT
            )
        approval = self._approval
        if approval is None:
            self._log("approval_timed_out")
            return decision.model_copy(
                update={"action": EscalateAction(reason=APPROVAL_TIMEOUT_REASON)}
            )
        self._status.approval = approval
        self._log("approval_received", approved=approval.approved)
        if approval.approved:
            return decision
        message = "Your refund request was reviewed and not approved."
        if approval.comment:
            message += f" Reviewer comment: {approval.comment}"
        return decision.model_copy(
            update={
                "action": ReplyAction(message=message, article_ids=[REFUND_POLICY_ARTICLE]),
            }
        )

    @workflow.query
    def status(self) -> WorkflowStatus:
        return self._status

    @workflow.signal
    def submit_approval(self, approval: ApprovalInput) -> None:
        # Only the first approval received while waiting counts; a late or repeated one is
        # ignored, so it can never trigger a refund.
        if self._status.step != WorkflowStep.AWAITING_APPROVAL or self._approval is not None:
            self._log("approval_ignored", step=self._status.step.value)
            return
        self._approval = approval

    def _set_step(self, step: WorkflowStep) -> None:
        self._status.step = step
        self._status.updated_at = workflow.now()
        self._log("step_changed", step=step.value)

    def _log(self, event: str, **fields) -> None:
        workflow.logger.info(event, extra={"ticket_id": self._ticket.ticket_id, **fields})


def _attempts(policy: RetryPolicy) -> str:
    return f"{policy.maximum_attempts} attempts"


def _failure_reason(err: ActivityError, exhausted_prefix: str) -> str:
    """A readable reason from the activity failure's cause."""
    cause = err.cause
    if isinstance(cause, ApplicationError) and (
        cause.non_retryable or err.retry_state == RetryState.NON_RETRYABLE_FAILURE
    ):
        return cause.message
    if isinstance(cause, ActivityTimeoutError):
        kind = f"TimeoutError ({cause.type.name})" if cause.type else "TimeoutError"
    elif isinstance(cause, ApplicationError):
        kind = cause.type or "ApplicationError"
    else:
        kind = type(cause).__name__
    return f"{exhausted_prefix}: {kind}"
