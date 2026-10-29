import json
from pathlib import Path

import pytest

from app.adapters.fake_llm import FakeChatModel
from app.agent.loop import run_agent
from app.agent.tools import ToolExecutor
from app.data.store import DataStore
from app.domain.models import Ticket

STORE = DataStore()
SAMPLES = {
    t["ticket_id"]: Ticket.model_validate(t)
    for t in json.loads((Path(__file__).parents[1] / "samples" / "tickets.json").read_text())
}

# Expectations table from the spec: tools called and the proposed decision.
EXPECTED = {
    "T-1": (
        [("get_customer", {}), ("search_kb", {"query": "password"})],
        (
            "account",
            "normal",
            {
                "kind": "reply",
                "message": "Open the sign-in page, choose 'Forgot password' and follow the link "
                "we email you. The link works for 30 minutes.",
                "article_ids": ["KB-1"],
            },
        ),
    ),
    "T-2": (
        [("get_customer", {}), ("get_invoices", {}), ("search_kb", {"query": "refund"})],
        ("billing", "high", {"kind": "refund", "invoice_id": "INV-1002", "amount_eur": "49.00"}),
    ),
    "T-3": (
        [("get_customer", {}), ("search_kb", {"query": "outages"})],
        (
            "technical",
            "urgent",
            {"kind": "escalate", "reason": "outage reported by enterprise customer"},
        ),
    ),
    "T-4": (
        [("get_customer", {}), ("get_invoices", {}), ("search_kb", {"query": "suspended"})],
        ("account", "high", {"kind": "reply", "article_ids": ["KB-4"]}),
    ),
    "T-5": (
        [("get_customer", {})],
        ("other", "low", {"kind": "close", "reason": "not a support request"}),
    ),
    # No invoice in the ticket: the naive fake takes the stated amount and the customer's
    # first paid invoice. The rules turn this into an escalation.
    "T-6": (
        [("get_customer", {}), ("get_invoices", {}), ("search_kb", {"query": "refund"})],
        ("billing", "high", {"kind": "refund", "invoice_id": "INV-1001", "amount_eur": "5000.00"}),
    ),
}


class RecordingModel:
    def __init__(self) -> None:
        self.inner = FakeChatModel()
        self.replies = []

    async def complete(self, messages, tools):
        reply = await self.inner.complete(messages, tools)
        self.replies.append(reply)
        return reply


@pytest.mark.parametrize("ticket_id", sorted(EXPECTED))
async def test_fake_model_follows_expectations_table(ticket_id: str) -> None:
    ticket = SAMPLES[ticket_id]
    model = RecordingModel()
    decision = await run_agent(ticket, model, ToolExecutor(ticket.customer_id, STORE))

    expected_tools, (category, priority, action) = EXPECTED[ticket_id]
    calls = [(c.name, json.loads(c.arguments_json)) for r in model.replies for c in r.tool_calls]
    assert calls == expected_tools
    assert (decision.category, decision.priority) == (category, priority)
    dumped = decision.action.model_dump()
    for key, value in action.items():
        assert dumped[key] == value


async def test_fake_never_decides_on_turn_one() -> None:
    for ticket in SAMPLES.values():
        reply = await FakeChatModel().complete(
            [{"role": "system", "content": ""}, {"role": "user", "content": ticket.subject}], []
        )
        assert reply.content is None
        assert reply.tool_calls[0].name == "get_customer"


async def test_t4_reply_mentions_overdue_invoice() -> None:
    ticket = SAMPLES["T-4"]
    decision = await run_agent(ticket, FakeChatModel(), ToolExecutor(ticket.customer_id, STORE))
    assert "INV-4001" in decision.action.model_dump()["message"]


async def test_t2_refunds_the_duplicate_of_two_equal_invoices_in_one_month() -> None:
    # INV-1001 and INV-1002 are both paid, both 2026-09, both 49.00: INV-1002 is the extra one.
    ticket = SAMPLES["T-2"]
    decision = await run_agent(ticket, FakeChatModel(), ToolExecutor(ticket.customer_id, STORE))
    assert decision.action.model_dump() == {
        "kind": "refund",
        "invoice_id": "INV-1002",
        "amount_eur": "49.00",
    }


async def test_t4_reply_follows_kb4() -> None:
    ticket = SAMPLES["T-4"]
    decision = await run_agent(ticket, FakeChatModel(), ToolExecutor(ticket.customer_id, STORE))
    assert decision.action.model_dump()["message"] == (
        "Your account is suspended because invoice INV-4001 is overdue. "
        "Pay the invoice to unlock the account."
    )
