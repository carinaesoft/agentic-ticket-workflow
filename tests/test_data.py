import json
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.data.store import DataStore
from app.domain.models import (
    ActionKind,
    Category,
    Decision,
    Priority,
    ProposedDecision,
    RefundAction,
    Ticket,
)

SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "tickets.json"


@pytest.fixture(scope="module")
def store() -> DataStore:
    return DataStore()


def test_reference_data_parses(store: DataStore) -> None:
    assert store.get_customer("C-101") is not None
    assert store.kb_ids() == ["KB-1", "KB-2", "KB-3", "KB-4", "KB-5"]
    assert all(isinstance(i.amount_eur, Decimal) for i in store.invoices_for("C-101"))


def test_sample_tickets_parse() -> None:
    tickets = [Ticket.model_validate(t) for t in json.loads(SAMPLES.read_text())]
    assert [t.ticket_id for t in tickets] == [f"T-{n}" for n in range(1, 8)]


def test_enums_match_allowed_values(store: DataStore) -> None:
    allowed = store.allowed_values
    assert allowed["categories"] == [c.value for c in Category]
    assert allowed["priorities"] == [p.value for p in Priority]
    assert allowed["action_kinds"] == [k.value for k in ActionKind]


def test_invoices_for_returns_only_that_customers_invoices(store: DataStore) -> None:
    invoices = store.invoices_for("C-101")
    assert {i.invoice_id for i in invoices} == {"INV-1001", "INV-1002"}
    assert all(i.customer_id == "C-101" for i in invoices)


def test_search_kb_ranks_password_article_first(store: DataStore) -> None:
    results = store.search_kb("forgot password")
    assert results[0].article_id == "KB-1"
    assert len(results) <= 3


def test_search_kb_without_matches_is_empty(store: DataStore) -> None:
    assert store.search_kb("zzzz") == []


def test_unknown_customer_is_none(store: DataStore) -> None:
    assert store.get_customer("C-999") is None
    assert store.invoices_for("C-999") == []


@pytest.mark.parametrize(
    "ticket_id",
    ["", "a" * 65, "T 1", "T/1", "../etc"],
    ids=["empty", "long", "space", "slash", "dots"],
)
def test_ticket_id_is_restricted(ticket_id: str) -> None:
    with pytest.raises(ValidationError):
        Ticket(ticket_id=ticket_id, customer_id="C-1", subject="s", body="b")


def test_ticket_text_limits() -> None:
    with pytest.raises(ValidationError):
        Ticket(ticket_id="T", customer_id="C-1", subject="s" * 201, body="b")
    with pytest.raises(ValidationError):
        Ticket(ticket_id="T", customer_id="C-1", subject="s", body="b" * 5001)


def test_proposed_decision_keeps_free_action_fields() -> None:
    raw = '{"category": "x", "priority": "y", "action": {"kind": "refund", "amount_eur": "1"}}'
    proposed = ProposedDecision.model_validate_json(raw)
    assert proposed.action.kind == "refund"
    assert proposed.action.model_dump()["amount_eur"] == "1"


def test_proposed_decision_requires_shape() -> None:
    with pytest.raises(ValidationError):
        ProposedDecision.model_validate_json('{"category": "billing", "priority": "high"}')


def test_decision_action_is_discriminated_on_kind() -> None:
    decision = Decision.model_validate(
        {
            "category": "billing",
            "priority": "high",
            "action": {"kind": "refund", "invoice_id": "INV-1", "amount_eur": "9.50"},
        }
    )
    assert isinstance(decision.action, RefundAction)
    assert decision.action.amount_eur == Decimal("9.50")
