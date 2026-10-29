"""Business rules that validate an agent decision.

``validate_decision`` is a pure function: it runs inside the workflow on every decision and
is the only way to turn an untyped ``ProposedDecision`` into a typed ``Decision``. Any
violation turns the decision into an ``escalate`` action naming the violated rules, so no
ticket text or model output can push an invalid action through.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel

from app.domain.models import (
    Action,
    ActionKind,
    Category,
    CloseAction,
    Decision,
    DecisionContext,
    EscalateAction,
    Priority,
    ProposedDecision,
    RefundAction,
    ReplyAction,
    Ticket,
)

MAX_MESSAGE_CHARS = 2000
MAX_REASON_CHARS = 500
REJECTED_PREFIX = "decision rejected by rules: "
CENT = Decimal("0.01")
# Plain decimal notation only: Decimal() alone also takes "4_9", "+49" or non-ASCII digits.
DECIMAL_STRING = re.compile(r"-?[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)?")
PAID = "paid"  # only a paid invoice can be refunded


class ValidationOutcome(BaseModel):
    decision: Decision
    errors: list[str]


def validate_decision(
    proposed: ProposedDecision, ticket: Ticket, ctx: DecisionContext
) -> ValidationOutcome:
    errors: list[str] = []

    category = _enum_value(Category, proposed.category)
    if category is None:
        errors.append(f"unknown category {proposed.category!r}")
    priority = _enum_value(Priority, proposed.priority)
    if priority is None:
        errors.append(f"unknown priority {proposed.priority!r}")

    fields = proposed.action.model_dump()
    action: Action | None = None
    match proposed.action.kind:
        case ActionKind.REPLY:
            action = _check_reply(fields, ctx, errors)
        case ActionKind.REFUND:
            action = _check_refund(fields, ticket, ctx, errors)
        case ActionKind.ESCALATE:
            action = EscalateAction(reason=_check_reason(fields, "escalate", errors))
        case ActionKind.CLOSE:
            action = CloseAction(reason=_check_reason(fields, "close", errors))
        case other:
            errors.append(f"unknown action kind {other!r}")

    if errors or action is None:
        return ValidationOutcome(
            decision=Decision(
                category=category or Category.OTHER,
                priority=priority or Priority.NORMAL,
                action=EscalateAction(reason=REJECTED_PREFIX + "; ".join(errors)),
            ),
            errors=errors,
        )
    return ValidationOutcome(
        decision=Decision(category=category, priority=priority, action=action),
        errors=[],
    )


def _enum_value[E: (Category, Priority)](enum: type[E], value: str) -> E | None:
    try:
        return enum(value)
    except ValueError:
        return None


def _check_reply(fields: dict[str, Any], ctx: DecisionContext, errors: list[str]) -> ReplyAction:
    message = fields.get("message")
    if not isinstance(message, str) or not message.strip():
        errors.append("reply message must be a non-empty string")
        message = ""
    elif len(message) > MAX_MESSAGE_CHARS:
        errors.append(f"reply message is longer than {MAX_MESSAGE_CHARS} characters")

    article_ids = fields.get("article_ids", [])
    if not isinstance(article_ids, list) or not all(isinstance(a, str) for a in article_ids):
        errors.append("reply article_ids must be a list of strings")
        article_ids = []
    known = set(ctx.kb_ids)
    for article_id in article_ids:
        if article_id not in known:
            errors.append(f"reply cites unknown article {article_id!r}")
    return ReplyAction(message=message, article_ids=article_ids)


def _check_refund(
    fields: dict[str, Any], ticket: Ticket, ctx: DecisionContext, errors: list[str]
) -> RefundAction | None:
    invoice_id = fields.get("invoice_id")
    amount = _to_decimal(fields.get("amount_eur"))
    if not isinstance(invoice_id, str) or not invoice_id:
        errors.append("refund requires an invoice_id")
        return None
    if amount is None:
        errors.append("refund requires amount_eur as a decimal number")
        return None
    try:
        cents = amount.quantize(CENT)
    except InvalidOperation:  # too many digits to express in cents
        errors.append("refund amount is out of range")
        return None
    if cents != amount:
        errors.append(f"refund amount {amount} has more than 2 decimal places")
        return None
    amount = cents

    if amount <= 0:
        errors.append(f"refund amount {amount} must be greater than zero")
    invoice = next((i for i in ctx.invoices if i.invoice_id == invoice_id), None)
    if invoice is None:
        errors.append(f"invoice {invoice_id} not found for customer {ticket.customer_id}")
    elif invoice.customer_id != ticket.customer_id:
        errors.append(f"invoice {invoice_id} does not belong to customer {ticket.customer_id}")
    elif invoice.status != PAID:
        errors.append(f"invoice {invoice_id} is not paid (status: {invoice.status})")
    elif amount > invoice.amount_eur:
        errors.append(
            f"refund amount {amount} exceeds invoice {invoice_id} amount {invoice.amount_eur}"
        )
    return RefundAction(invoice_id=invoice_id, amount_eur=amount)


def _check_reason(fields: dict[str, Any], kind: str, errors: list[str]) -> str:
    reason = fields.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        errors.append(f"{kind} reason must be a non-empty string")
        return ""
    if len(reason) > MAX_REASON_CHARS:
        errors.append(f"{kind} reason is longer than {MAX_REASON_CHARS} characters")
    return reason


def _to_decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        return None
    if isinstance(value, str) and not DECIMAL_STRING.fullmatch(value.strip()):
        return None
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        return None
    return amount if amount.is_finite() else None
