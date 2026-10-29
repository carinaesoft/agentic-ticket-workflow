"""Fake Helpdesk API with failure injection and an idempotency store.

Stands in for an external Helpdesk. It fails transiently at a configurable rate, either
*before* the effect (nothing happened) or *after* it ("response lost": the effect happened
but the caller saw an error). An idempotency key makes a retried call return the stored
result instead of repeating the effect.

The store lives in this process's memory: the at-most-once guarantee holds within one
worker process only. A real Helpdesk would honour the key on its side.
"""

from __future__ import annotations

import random

from app.domain.models import (
    Action,
    ActionKind,
    ActionResult,
    CloseAction,
    EscalateAction,
    RefundAction,
    ReplyAction,
)


class HelpdeskTransientError(Exception):
    """A temporary failure; the same call may succeed when retried."""


class HelpdeskRejected(Exception):
    """The Helpdesk refused the request; retrying will not change that."""


class FakeHelpdesk:
    def __init__(
        self,
        failure_rate: float = 0.0,
        lost_response_rate: float = 0.0,
        rng: random.Random | None = None,
    ) -> None:
        self.failure_rate = failure_rate
        self.lost_response_rate = lost_response_rate
        self._rng = rng or random.Random()
        self._results: dict[str, tuple[Action, ActionResult]] = {}
        self.replies: list[ReplyAction] = []
        self.refunds: list[RefundAction] = []
        self.escalations: list[EscalateAction] = []
        self.closures: list[CloseAction] = []

    def perform(self, key: str, action: Action) -> ActionResult:
        stored = self._results.get(key)
        if stored is not None:
            stored_action, result = stored
            if stored_action != action:
                raise HelpdeskRejected(f"idempotency key {key} was used for a different action")
            return result

        if self._rng.random() < self.failure_rate:
            raise HelpdeskTransientError("helpdesk temporarily unavailable")

        result = self._apply(key, action)
        self._results[key] = (action, result)

        if self._rng.random() < self.lost_response_rate:
            raise HelpdeskTransientError("helpdesk response lost after the action was applied")
        return result

    def _apply(self, key: str, action: Action) -> ActionResult:
        reference = f"HD-{len(self._results) + 1:05d}"
        match action:
            case ReplyAction():
                self.replies.append(action)
                message = "reply sent to customer"
            case RefundAction():
                self.refunds.append(action)
                message = f"refund of {action.amount_eur} EUR issued for {action.invoice_id}"
            case EscalateAction():
                self.escalations.append(action)
                message = "escalated to a human agent"
            case CloseAction():
                self.closures.append(action)
                message = "ticket closed"
            case _:
                raise HelpdeskRejected(f"unsupported action {action!r}")
        return ActionResult(
            kind=ActionKind(action.kind),
            helpdesk_reference=reference,
            idempotency_key=key,
            outcome_message=message,
        )
