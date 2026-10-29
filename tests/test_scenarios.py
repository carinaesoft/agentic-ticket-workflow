"""End to end in the time-skipping server: the real workflow, the real activities, the fake
model and the fake Helpdesk with a scripted failure sequence, for the seven sample tickets."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from app.activities import TicketActivities
from app.adapters.fake_llm import FakeChatModel
from app.adapters.helpdesk import FakeHelpdesk
from app.data.store import DataStore
from app.domain.models import ApprovalInput, Ticket, WorkflowStatus, WorkflowStep
from app.logging import JsonFormatter, workflow_id_for
from app.worker import build_worker
from app.workflows.ticket import TicketWorkflow

SAMPLES = [
    Ticket.model_validate(t)
    for t in json.loads((Path(__file__).parents[1] / "samples" / "tickets.json").read_text())
]

FAIL, OK = 0.1, 0.9  # with both rates at 0.5: below fails, above passes
# One Helpdesk call draws once when it fails before the effect, twice when the effect is
# applied (before + "response lost" check), and never when the key is already stored.
# The tickets run one after another, so this sequence is consumed in this order.
HELPDESK_SCRIPT = {
    "T-1": [FAIL, OK, OK],  # transient failure, then success
    "T-2": [FAIL, OK, FAIL],  # transient failure, then refund applied but response lost
    "T-3": [OK, OK],
    "T-4": [OK, FAIL],  # effect applied, response lost; the retry hits the stored result
    "T-5": [FAIL, FAIL, OK, OK],  # two transient failures in a row (never 5)
    "T-6": [OK, OK],
    "T-7": [FAIL, OK, OK],
}


class ScriptedRandom(random.Random):
    def __init__(self, values: list[float]) -> None:
        super().__init__()
        self.values = list(values)

    def random(self) -> float:
        return self.values.pop(0)


async def run_ticket(env, task_queue: str, ticket: Ticket) -> WorkflowStatus:
    handle = await env.client.start_workflow(
        TicketWorkflow.run,
        ticket,
        id=workflow_id_for(ticket.ticket_id),
        task_queue=task_queue,
    )
    if ticket.ticket_id.startswith("T-2-"):
        for _ in range(200):
            status = await handle.query(TicketWorkflow.status)
            if status.step == WorkflowStep.AWAITING_APPROVAL:
                break
            await asyncio.sleep(0.05)
        await handle.signal(
            TicketWorkflow.submit_approval, ApprovalInput(approved=True, reviewer="billing-lead")
        )
    return await handle.result()


@pytest.fixture
def scenario(caplog):
    caplog.set_level(logging.INFO)
    rng = ScriptedRandom([v for values in HELPDESK_SCRIPT.values() for v in values])
    helpdesk = FakeHelpdesk(failure_rate=0.5, lost_response_rate=0.5, rng=rng)
    activities = TicketActivities(DataStore(), FakeChatModel(), helpdesk)
    run_id = uuid.uuid4().hex[:6]
    tickets = [t.model_copy(update={"ticket_id": f"{t.ticket_id}-{run_id}"}) for t in SAMPLES]
    return activities, helpdesk, rng, tickets


async def test_sample_tickets_end_to_end(env, scenario, caplog) -> None:
    activities, helpdesk, rng, tickets = scenario
    task_queue = f"tq-{uuid.uuid4()}"
    async with build_worker(env.client, task_queue, activities):
        results = {
            t.ticket_id.rsplit("-", 1)[0]: await run_ticket(env, task_queue, t) for t in tickets
        }

    assert rng.values == []  # the whole failure script was consumed
    for status in results.values():
        assert status.step == WorkflowStep.COMPLETED, status

    def action(ticket_id: str) -> dict:
        return results[ticket_id].decision.action.model_dump()

    triage = {t: (r.decision.category.value, r.decision.priority.value) for t, r in results.items()}
    assert triage == {
        "T-1": ("account", "normal"),
        "T-2": ("billing", "high"),
        "T-3": ("technical", "urgent"),
        "T-4": ("account", "high"),
        "T-5": ("other", "low"),
        "T-6": ("billing", "high"),
        "T-7": ("other", "normal"),
    }

    assert action("T-1")["kind"] == "reply" and action("T-1")["article_ids"] == ["KB-1"]

    assert action("T-2") == {
        "kind": "refund",
        "invoice_id": "INV-1002",
        "amount_eur": Decimal("49.00"),
    }
    assert results["T-2"].approval.approved is True
    assert len(helpdesk.refunds) == 1  # one refund despite a failure and a lost response
    assert results["T-2"].result.idempotency_key == f"{results['T-2'].workflow_id}:refund"

    assert action("T-3") == {"kind": "escalate", "reason": "outage reported by enterprise customer"}
    assert action("T-4")["kind"] == "reply" and action("T-4")["article_ids"] == ["KB-4"]
    assert "INV-4001" in action("T-4")["message"]
    assert action("T-5") == {"kind": "close", "reason": "not a support request"}

    assert results["T-6"].proposed_decision.action.kind == "refund"
    assert action("T-6")["kind"] == "escalate"
    assert action("T-6")["reason"] == (
        "decision rejected by rules: refund amount 5000.00 exceeds invoice INV-1001 amount 49.00"
    )
    assert results["T-6"].approval is None

    assert results["T-7"].proposed_decision is None
    assert action("T-7") == {"kind": "escalate", "reason": "unknown customer C-999"}

    assert [r.kind for r in helpdesk.replies] == ["reply", "reply"]
    assert len(helpdesk.escalations) == 3
    assert len(helpdesk.closures) == 1

    # Every log line about a ticket carries both its ticket_id and its workflow_id.
    formatter = JsonFormatter()
    for ticket in tickets:
        workflow_id = workflow_id_for(ticket.ticket_id)
        lines = [json.loads(formatter.format(r)) for r in caplog.records]
        about = [
            e for e in lines if ticket.ticket_id in (e["ticket_id"], str(e["workflow_id"])[7:])
        ]
        assert about, ticket.ticket_id
        for entry in about:
            assert (entry["ticket_id"], entry["workflow_id"]) == (ticket.ticket_id, workflow_id)
    events = {r.msg for r in caplog.records}
    assert {"step_changed", "tool_called", "action_executed", "helpdesk_transient_error"} <= events
