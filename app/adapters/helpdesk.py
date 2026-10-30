"""Fake Helpdesk API with failure injection and an idempotency store.

Stands in for an external Helpdesk. It fails transiently at a configurable rate, either
*before* the effect (nothing happened) or *after* it ("response lost": the effect happened
but the caller saw an error). An idempotency key makes a retried call return the stored
result instead of repeating the effect, and ``lookup`` answers whether an action was
recorded under a key (used to reconcile after every attempt lost its response).

The store is one SQLite table, in the file at ``store_path``: the at-most-once guarantee then
survives a new process and holds between instances on the same file. Without a path it lives
in this instance's memory and ends with it. A real Helpdesk would honour the key on its side.
"""

from __future__ import annotations

import random
import sqlite3

from pydantic import TypeAdapter

from app.domain.models import (
    Action,
    ActionKind,
    ActionResult,
    CloseAction,
    EscalateAction,
    RefundAction,
    ReplyAction,
)

# How long a call waits for another instance's transaction on the same file.
STORE_TIMEOUT_SECONDS = 5.0

_ACTION: TypeAdapter[Action] = TypeAdapter(Action)


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
        store_path: str | None = None,
    ) -> None:
        self.failure_rate = failure_rate
        self.lost_response_rate = lost_response_rate
        self._rng = rng or random.Random()
        # Activities are async and run on the worker's event loop, so one connection is enough;
        # sqlite3 refuses a use from another thread. Autocommit: BEGIN IMMEDIATE is explicit.
        self._db = sqlite3.connect(
            store_path or ":memory:", timeout=STORE_TIMEOUT_SECONDS, isolation_level=None
        )
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS helpdesk_actions "
            "(key TEXT PRIMARY KEY, action_json TEXT NOT NULL, result_json TEXT NOT NULL)"
        )
        self.replies: list[ReplyAction] = []
        self.refunds: list[RefundAction] = []
        self.escalations: list[EscalateAction] = []
        self.closures: list[CloseAction] = []

    def perform(self, key: str, action: Action) -> ActionResult:
        # The write lock is taken before the key is checked, so two instances cannot both miss
        # it. Leaving the block commits; an exception rolls back.
        self._db.execute("BEGIN IMMEDIATE")
        with self._db:
            stored = self._db.execute(
                "SELECT action_json, result_json FROM helpdesk_actions WHERE key = ?", (key,)
            ).fetchone()
            if stored is not None:
                if _ACTION.validate_json(stored[0]) != action:
                    raise HelpdeskRejected(f"idempotency key {key} was used for a different action")
                return ActionResult.model_validate_json(stored[1])

            if self._rng.random() < self.failure_rate:
                raise HelpdeskTransientError("helpdesk temporarily unavailable")

            [count] = self._db.execute("SELECT COUNT(*) FROM helpdesk_actions").fetchone()
            result = self._apply(key, action, f"HD-{count + 1:05d}")
            self._db.execute(
                "INSERT INTO helpdesk_actions (key, action_json, result_json) VALUES (?, ?, ?)",
                (key, _ACTION.dump_json(action).decode(), result.model_dump_json()),
            )

        if self._rng.random() < self.lost_response_rate:
            raise HelpdeskTransientError("helpdesk response lost after the action was applied")
        return result

    def lookup(self, key: str) -> ActionResult | None:
        """The stored result for ``key``, or ``None`` when no action was recorded under it."""
        stored = self._db.execute(
            "SELECT result_json FROM helpdesk_actions WHERE key = ?", (key,)
        ).fetchone()
        return ActionResult.model_validate_json(stored[0]) if stored is not None else None

    def _apply(self, key: str, action: Action, reference: str) -> ActionResult:
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
