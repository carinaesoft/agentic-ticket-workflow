import random
from decimal import Decimal

import httpx
import openai
import pytest
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from app.activities import ActionRequest, TicketActivities, idempotency_key
from app.adapters.fake_llm import FakeChatModel
from app.adapters.helpdesk import FakeHelpdesk
from app.adapters.llm import LLMConfigError
from app.data.store import DataStore
from app.domain.models import CloseAction, RefundAction, Ticket
from tests.scripted_model import ScriptedModel, answer

STORE = DataStore()
T1 = Ticket(ticket_id="T-1", customer_id="C-102", subject="Cannot log in", body="forgot password")


def activities(model=None, helpdesk=None) -> TicketActivities:
    return TicketActivities(
        STORE, model or FakeChatModel(), helpdesk or FakeHelpdesk(rng=random.Random(0))
    )


async def test_unknown_customer_is_non_retryable() -> None:
    ticket = T1.model_copy(update={"customer_id": "C-999"})
    model = ScriptedModel([])
    with pytest.raises(ApplicationError) as excinfo:
        await ActivityEnvironment().run(activities(model).decide_ticket, ticket)
    assert excinfo.value.type == "UnknownCustomer"
    assert excinfo.value.non_retryable
    assert excinfo.value.message == "unknown customer C-999"
    assert model.calls == []  # no tokens spent


async def test_fake_llm_t1_gives_reply_decision_and_context() -> None:
    out = await ActivityEnvironment().run(activities().decide_ticket, T1)
    assert out.decision.action.kind == "reply"
    assert out.decision.category == "account"
    assert out.context.customer.customer_id == "C-102"
    assert out.context.kb_ids == STORE.kb_ids()


async def test_unreadable_model_output_is_non_retryable() -> None:
    model = ScriptedModel([answer("not json")], repeat_last=True)
    with pytest.raises(ApplicationError) as excinfo:
        await ActivityEnvironment().run(activities(model).decide_ticket, T1)
    assert excinfo.value.type == "AgentOutputInvalid"
    assert excinfo.value.non_retryable


class FailingModel:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    async def complete(self, messages, tools):
        raise self.exc


def _request() -> httpx.Request:
    return httpx.Request("POST", "https://api.example.invalid/v1/chat/completions")


async def test_llm_timeout_stays_retryable() -> None:
    model = FailingModel(openai.APITimeoutError(request=_request()))
    with pytest.raises(openai.APITimeoutError):
        await ActivityEnvironment().run(activities(model).decide_ticket, T1)


def _status_error(status: int) -> openai.APIStatusError:
    """The error class the OpenAI SDK raises for this status."""
    response = httpx.Response(status, request=_request())
    client = openai.OpenAI(api_key="test-key", base_url="https://api.example.invalid/v1")
    return client._make_status_error("provider error", body=None, response=response)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422])
async def test_llm_client_error_is_non_retryable_with_reason(status: int) -> None:
    exc = _status_error(status)
    model = FailingModel(exc)
    with pytest.raises(ApplicationError) as excinfo:
        await ActivityEnvironment().run(activities(model).decide_ticket, T1)
    assert excinfo.value.type == "LLMRequestRejected"
    assert excinfo.value.non_retryable
    assert excinfo.value.message == (
        f"LLM request rejected by the provider: HTTP {status} ({type(exc).__name__}), not retried"
    )


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
async def test_llm_transient_status_stays_retryable(status: int) -> None:
    exc = _status_error(status)
    model = FailingModel(exc)
    with pytest.raises(openai.APIStatusError) as excinfo:
        await ActivityEnvironment().run(activities(model).decide_ticket, T1)
    assert excinfo.value is exc


async def test_llm_connection_error_stays_retryable() -> None:
    model = FailingModel(openai.APIConnectionError(request=_request()))
    with pytest.raises(openai.APIConnectionError):
        await ActivityEnvironment().run(activities(model).decide_ticket, T1)


async def test_llm_config_error_is_non_retryable() -> None:
    model = FailingModel(LLMConfigError("LLM_PROVIDER=openai requires OPENAI_API_KEY"))
    with pytest.raises(ApplicationError) as excinfo:
        await ActivityEnvironment().run(activities(model).decide_ticket, T1)
    assert excinfo.value.type == "LLMConfigError"
    assert excinfo.value.non_retryable
    assert "OPENAI_API_KEY" in excinfo.value.message


async def test_transient_helpdesk_error_is_retryable() -> None:
    helpdesk = FakeHelpdesk(failure_rate=1, rng=random.Random(0))
    request = ActionRequest(
        workflow_id="ticket-T-5", ticket_id="T-5", action=CloseAction(reason="x")
    )
    with pytest.raises(ApplicationError) as excinfo:
        await ActivityEnvironment().run(activities(helpdesk=helpdesk).execute_action, request)
    assert excinfo.value.type == "HelpdeskTransientError"
    assert not excinfo.value.non_retryable


async def test_helpdesk_rejection_is_non_retryable() -> None:
    helpdesk = FakeHelpdesk(rng=random.Random(0))
    acts = activities(helpdesk=helpdesk)
    env = ActivityEnvironment()
    refund = RefundAction(invoice_id="INV-1002", amount_eur=Decimal("49.00"))
    await env.run(acts.execute_action, ActionRequest(workflow_id="w", ticket_id="T", action=refund))
    other = refund.model_copy(update={"amount_eur": Decimal("1.00")})
    with pytest.raises(ApplicationError) as excinfo:
        await env.run(
            acts.execute_action, ActionRequest(workflow_id="w", ticket_id="T", action=other)
        )
    assert excinfo.value.type == "HelpdeskRejected"
    assert excinfo.value.non_retryable


async def test_idempotency_key_is_workflow_id_and_kind() -> None:
    helpdesk = FakeHelpdesk(rng=random.Random(0))
    refund = RefundAction(invoice_id="INV-1002", amount_eur=Decimal("49.00"))
    request = ActionRequest(workflow_id="ticket-T-2", ticket_id="T-2", action=refund)
    env = ActivityEnvironment()
    first = await env.run(activities(helpdesk=helpdesk).execute_action, request)
    second = await env.run(activities(helpdesk=helpdesk).execute_action, request)

    assert first.idempotency_key == "ticket-T-2:refund" == idempotency_key("ticket-T-2", refund)
    assert second == first
    assert len(helpdesk.refunds) == 1


async def test_lookup_action_result_reports_recorded_action_by_key() -> None:
    helpdesk = FakeHelpdesk(rng=random.Random(0))
    acts = activities(helpdesk=helpdesk)
    env = ActivityEnvironment()
    refund = RefundAction(invoice_id="INV-1002", amount_eur=Decimal("49.00"))
    request = ActionRequest(workflow_id="ticket-T-2", ticket_id="T-2", action=refund)
    assert await env.run(acts.lookup_action_result, request) is None

    executed = await env.run(acts.execute_action, request)
    assert await env.run(acts.lookup_action_result, request) == executed
    assert len(helpdesk.refunds) == 1
