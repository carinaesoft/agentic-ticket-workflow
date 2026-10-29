import subprocess
import sys
from decimal import Decimal
from typing import Any

import pytest

from app.data.store import DataStore
from app.domain.models import (
    Category,
    CloseAction,
    DecisionContext,
    EscalateAction,
    Invoice,
    Priority,
    ProposedDecision,
    RefundAction,
    ReplyAction,
    Ticket,
)
from app.domain.rules import validate_decision

STORE = DataStore()
TICKET = Ticket(ticket_id="T-2", customer_id="C-101", subject="Charged twice", body="Refund please")


def ctx_for(customer_id: str = "C-101", extra_invoices: list[Invoice] | None = None):
    return DecisionContext(
        customer=STORE.get_customer(customer_id),
        invoices=STORE.invoices_for(customer_id) + (extra_invoices or []),
        kb_ids=STORE.kb_ids(),
    )


def proposal(action: dict[str, Any], category: str = "billing", priority: str = "high"):
    return ProposedDecision.model_validate(
        {"category": category, "priority": priority, "action": action}
    )


def check(action: dict[str, Any], **kwargs):
    ctx = kwargs.pop("ctx", None) or ctx_for()
    return validate_decision(proposal(action, **kwargs), TICKET, ctx)


def assert_escalated(outcome, fragment: str) -> None:
    assert isinstance(outcome.decision.action, EscalateAction)
    assert outcome.decision.action.reason.startswith("decision rejected by rules: ")
    assert any(fragment in e for e in outcome.errors), outcome.errors
    assert fragment in outcome.decision.action.reason


# --- valid decisions come back typed --------------------------------------------------


def test_valid_reply_passes() -> None:
    out = check({"kind": "reply", "message": "Use the reset link.", "article_ids": ["KB-1"]})
    assert out.errors == []
    assert out.decision.category is Category.BILLING
    assert out.decision.priority is Priority.HIGH
    assert out.decision.action == ReplyAction(message="Use the reset link.", article_ids=["KB-1"])


def test_valid_close_passes() -> None:
    out = check({"kind": "close", "reason": "not a support request"})
    assert out.errors == []
    assert out.decision.action == CloseAction(reason="not a support request")


def test_valid_escalate_passes() -> None:
    out = check({"kind": "escalate", "reason": "outage"})
    assert out.errors == []
    assert out.decision.action == EscalateAction(reason="outage")


@pytest.mark.parametrize("amount", ["49.00", 49, 49.0, "0.01"])
def test_refund_on_own_invoice_within_amount_passes(amount) -> None:
    out = check({"kind": "refund", "invoice_id": "INV-1002", "amount_eur": amount})
    assert out.errors == []
    assert isinstance(out.decision.action, RefundAction)
    assert out.decision.action.amount_eur == Decimal(str(amount))


# --- violations escalate with a named reason ------------------------------------------


def test_unknown_category_escalates_and_falls_back_to_other() -> None:
    out = check({"kind": "close", "reason": "x"}, category="sales")
    assert_escalated(out, "unknown category 'sales'")
    assert out.decision.category is Category.OTHER
    assert out.decision.priority is Priority.HIGH


def test_unknown_priority_escalates_and_falls_back_to_normal() -> None:
    out = check({"kind": "close", "reason": "x"}, priority="critical")
    assert_escalated(out, "unknown priority 'critical'")
    assert out.decision.priority is Priority.NORMAL
    assert out.decision.category is Category.BILLING


def test_unknown_action_kind_escalates() -> None:
    assert_escalated(check({"kind": "delete_account"}), "unknown action kind 'delete_account'")


def test_refund_without_amount_escalates() -> None:
    out = check({"kind": "refund", "invoice_id": "INV-1002"})
    assert_escalated(out, "refund requires amount_eur")


def test_refund_without_invoice_escalates() -> None:
    assert_escalated(check({"kind": "refund", "amount_eur": "1"}), "refund requires an invoice_id")


@pytest.mark.parametrize("amount", ["abc", True, None, [1], "NaN", "Infinity"])
def test_refund_with_non_decimal_amount_escalates(amount) -> None:
    out = check({"kind": "refund", "invoice_id": "INV-1002", "amount_eur": amount})
    assert_escalated(out, "refund requires amount_eur")


def test_refund_over_invoice_amount_escalates() -> None:
    out = check({"kind": "refund", "invoice_id": "INV-1002", "amount_eur": "49.01"})
    assert_escalated(out, "exceeds invoice INV-1002 amount 49.00")


def test_refund_on_paid_invoice_passes() -> None:
    out = check({"kind": "refund", "invoice_id": "INV-1002", "amount_eur": "49.00"})
    assert out.errors == []
    assert out.decision.action == RefundAction(invoice_id="INV-1002", amount_eur=Decimal("49.00"))


def test_refund_on_unpaid_invoice_escalates() -> None:
    c104 = Ticket(ticket_id="T-4", customer_id="C-104", subject="Refund", body="Refund please")
    out = validate_decision(
        proposal({"kind": "refund", "invoice_id": "INV-4001", "amount_eur": "49.00"}),
        c104,
        ctx_for("C-104"),
    )
    assert_escalated(out, "invoice INV-4001 is not paid (status: overdue)")
    assert out.errors == ["invoice INV-4001 is not paid (status: overdue)"]


def test_refund_on_another_customers_invoice_escalates() -> None:
    # The scoped snapshot does not contain other customers' invoices at all.
    out = check({"kind": "refund", "invoice_id": "INV-3001", "amount_eur": "10"})
    assert_escalated(out, "invoice INV-3001 not found for customer C-101")


def test_refund_on_foreign_invoice_inside_snapshot_escalates() -> None:
    foreign = STORE.invoices_for("C-103")
    out = check(
        {"kind": "refund", "invoice_id": "INV-3001", "amount_eur": "10"},
        ctx=ctx_for(extra_invoices=foreign),
    )
    assert_escalated(out, "invoice INV-3001 does not belong to customer C-101")


def test_refund_on_unknown_invoice_escalates() -> None:
    out = check({"kind": "refund", "invoice_id": "INV-0000", "amount_eur": "10"})
    assert_escalated(out, "invoice INV-0000 not found")


@pytest.mark.parametrize("amount", ["0", "-5", -0.01])
def test_refund_with_zero_or_negative_amount_escalates(amount) -> None:
    out = check({"kind": "refund", "invoice_id": "INV-1002", "amount_eur": amount})
    assert_escalated(out, "must be greater than zero")


@pytest.mark.parametrize("amount", ["0.0000001", 1e-300, "12.345", "0.001"])
def test_refund_with_sub_cent_precision_escalates(amount) -> None:
    out = check({"kind": "refund", "invoice_id": "INV-1002", "amount_eur": amount})
    assert_escalated(out, "has more than 2 decimal places")


def test_refund_amount_too_large_for_cents_escalates() -> None:
    out = check({"kind": "refund", "invoice_id": "INV-1002", "amount_eur": "1e999999999"})
    assert_escalated(out, "refund amount is out of range")


@pytest.mark.parametrize(
    ("amount", "expected"), [("1E+1", "10.00"), (" 12 ", "12.00"), (49, "49.00")]
)
def test_refund_amount_is_normalised_to_cents(amount, expected) -> None:
    out = check({"kind": "refund", "invoice_id": "INV-1002", "amount_eur": amount})
    assert out.errors == []
    assert str(out.decision.action.amount_eur) == expected


def test_reply_with_unknown_article_escalates() -> None:
    out = check({"kind": "reply", "message": "See this.", "article_ids": ["KB-1", "KB-99"]})
    assert_escalated(out, "reply cites unknown article 'KB-99'")


@pytest.mark.parametrize(
    ("action", "fragment"),
    [
        ({"kind": "reply", "message": "  "}, "reply message must be a non-empty string"),
        ({"kind": "reply", "message": "x" * 2001}, "longer than 2000"),
        ({"kind": "reply", "message": "ok", "article_ids": "KB-1"}, "must be a list of strings"),
        ({"kind": "escalate"}, "escalate reason must be a non-empty string"),
        ({"kind": "close", "reason": "x" * 501}, "close reason is longer than 500"),
    ],
)
def test_malformed_action_fields_escalate(action, fragment) -> None:
    assert_escalated(check(action), fragment)


def test_t6_shaped_decision_escalates() -> None:
    out = check({"kind": "refund", "invoice_id": "INV-1001", "amount_eur": "5000.00"})
    assert_escalated(out, "refund amount 5000.00 exceeds invoice INV-1001 amount 49.00")


def test_multiple_violations_are_all_named() -> None:
    out = check({"kind": "teleport"}, category="sales", priority="asap")
    assert len(out.errors) == 3
    assert out.decision.action.reason.count(";") == 2


def test_domain_imports_no_framework_or_sdk() -> None:
    code = (
        "import sys, app.domain.models, app.domain.rules;"
        "bad = [m for m in ('fastapi', 'temporalio', 'openai') if m in sys.modules];"
        "assert not bad, bad"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
