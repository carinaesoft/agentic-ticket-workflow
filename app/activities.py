"""Temporal activities.

Everything non-deterministic lives here: the LLM agent loop (``decide_ticket``), the
Helpdesk side effect (``execute_action``) and the read-only reconciliation that asks the
Helpdesk whether an action was recorded (``lookup_action_result``). Errors that retrying
cannot fix are raised as ``ApplicationError(non_retryable=True)`` at the raise site;
anything else propagates and is retried by the workflow's retry policy.
"""

from __future__ import annotations

import openai
from temporalio import activity
from temporalio.exceptions import ApplicationError

from app.adapters.helpdesk import FakeHelpdesk, HelpdeskRejected, HelpdeskTransientError
from app.adapters.llm import ChatModel, LLMConfigError
from app.agent.loop import AgentLimits, AgentOutputInvalid, AgentTurnLimit, run_agent
from app.agent.tools import ToolExecutor
from app.data.store import DataStore
from app.domain.models import (
    Action,
    ActionRequest,
    ActionResult,
    DecideOutput,
    DecisionContext,
    Ticket,
)

# Provider HTTP statuses that mean the request itself is wrong (parameters, key, access,
# model, conflict, unprocessable input): a retry would fail the same way. Everything else
# (408, 429, 5xx, timeouts, connection errors) propagates and is retried.
NON_RETRYABLE_LLM_STATUSES = frozenset({400, 401, 403, 404, 409, 422})


def idempotency_key(workflow_id: str, action: Action) -> str:
    """One effective action per workflow: stable across retries and worker restarts."""
    return f"{workflow_id}:{action.kind}"


class TicketActivities:
    def __init__(
        self,
        store: DataStore,
        model: ChatModel,
        helpdesk: FakeHelpdesk,
        limits: AgentLimits | None = None,
    ) -> None:
        self._store = store
        self._model = model
        self._helpdesk = helpdesk
        self._limits = limits or AgentLimits()

    @activity.defn(name="decide_ticket")
    async def decide_ticket(self, ticket: Ticket) -> DecideOutput:
        extra = {"ticket_id": ticket.ticket_id}
        activity.logger.info(
            "decide_started",
            extra={**extra, "body_length": len(ticket.body), "subject_length": len(ticket.subject)},
        )
        customer = self._store.get_customer(ticket.customer_id)
        if customer is None:
            raise ApplicationError(
                f"unknown customer {ticket.customer_id}", type="UnknownCustomer", non_retryable=True
            )

        try:
            proposed = await run_agent(
                ticket,
                self._model,
                ToolExecutor(ticket.customer_id, self._store),
                self._limits,
                logger=activity.logger,
                log_extra=extra,
            )
        except AgentOutputInvalid as exc:
            raise ApplicationError(str(exc), type="AgentOutputInvalid", non_retryable=True) from exc
        except AgentTurnLimit as exc:
            raise ApplicationError(str(exc), type="AgentTurnLimit", non_retryable=True) from exc
        except LLMConfigError as exc:
            raise ApplicationError(
                f"LLM configuration error: {exc}", type="LLMConfigError", non_retryable=True
            ) from exc
        except openai.APIStatusError as exc:
            if exc.status_code not in NON_RETRYABLE_LLM_STATUSES:
                raise
            raise ApplicationError(
                f"LLM request rejected by the provider: HTTP {exc.status_code} "
                f"({type(exc).__name__}), not retried",
                type="LLMRequestRejected",
                non_retryable=True,
            ) from exc

        return DecideOutput(
            decision=proposed,
            context=DecisionContext(
                customer=customer,
                invoices=self._store.invoices_for(ticket.customer_id),
                kb_ids=self._store.kb_ids(),
            ),
        )

    @activity.defn(name="execute_action")
    async def execute_action(self, request: ActionRequest) -> ActionResult:
        key = idempotency_key(request.workflow_id, request.action)
        extra = {"ticket_id": request.ticket_id, "action_kind": request.action.kind, "key": key}
        try:
            result = self._helpdesk.perform(key, request.action)
        except HelpdeskTransientError as exc:
            activity.logger.warning("helpdesk_transient_error", extra={**extra, "error": str(exc)})
            raise ApplicationError(str(exc), type="HelpdeskTransientError") from exc
        except HelpdeskRejected as exc:
            activity.logger.error("helpdesk_rejected", extra={**extra, "error": str(exc)})
            raise ApplicationError(str(exc), type="HelpdeskRejected", non_retryable=True) from exc
        activity.logger.info(
            "action_executed", extra={**extra, "helpdesk_reference": result.helpdesk_reference}
        )
        return result

    @activity.defn(name="lookup_action_result")
    async def lookup_action_result(self, request: ActionRequest) -> ActionResult | None:
        """Ask the Helpdesk, by idempotency key, whether the action was recorded."""
        key = idempotency_key(request.workflow_id, request.action)
        result = self._helpdesk.lookup(key)
        activity.logger.info(
            "action_lookup",
            extra={
                "ticket_id": request.ticket_id,
                "action_kind": request.action.kind,
                "key": key,
                "found": result is not None,
            },
        )
        return result
