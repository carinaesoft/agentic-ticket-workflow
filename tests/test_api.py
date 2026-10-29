"""HTTP API against the time-skipping server, with a worker running the real workflow and
fake activities."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import uuid

import httpx
import pytest
import pytest_asyncio
from temporalio import activity
from temporalio.client import WorkflowQueryFailedError, WorkflowQueryRejectedError
from temporalio.service import RPCError, RPCStatusCode
from temporalio.worker import Worker

from app.api.main import create_app
from app.api.request_log import ticket_id_from
from app.config import Settings
from app.domain.models import ActionRequest, ActionResult, DecideOutput, Ticket
from app.logging import JsonFormatter
from app.workflows.ticket import TicketWorkflow
from tests.test_workflow import REFUND, REPLY, decide_output


class Recorder:
    def __init__(self) -> None:
        self.decided: list[str] = []
        self.executed: list[ActionRequest] = []

    def activities(self) -> list:
        @activity.defn(name="decide_ticket")
        async def decide_ticket(ticket: Ticket) -> DecideOutput:
            self.decided.append(ticket.ticket_id)
            return decide_output(REFUND if ticket.subject == "refund" else REPLY)

        @activity.defn(name="execute_action")
        async def execute_action(request: ActionRequest) -> ActionResult:
            self.executed.append(request)
            return ActionResult(
                kind=request.action.kind,
                helpdesk_reference="HD-1",
                idempotency_key=f"{request.workflow_id}:{request.action.kind}",
                outcome_message="done",
            )

        return [decide_ticket, execute_action]


@pytest_asyncio.fixture
async def api(env):
    recorder = Recorder()
    task_queue = f"tq-{uuid.uuid4()}"
    settings = Settings.model_validate({"temporal_task_queue": task_queue})
    app = create_app(client=env.client, settings=settings)
    async with (
        Worker(
            env.client,
            task_queue=task_queue,
            workflows=[TicketWorkflow],
            activities=recorder.activities(),
        ),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http,
    ):
        yield http, recorder


def new_ticket(subject: str = "login") -> dict:
    return {
        "ticket_id": f"T-{uuid.uuid4().hex[:10]}",
        "customer_id": "C-101",
        "subject": subject,
        "body": "Please help.",
    }


async def wait_for(http: httpx.AsyncClient, ticket_id: str, step: str) -> dict:
    for _ in range(200):
        body = (await http.get(f"/tickets/{ticket_id}")).json()
        if body.get("step") == step:
            return body
        await asyncio.sleep(0.05)
    raise AssertionError(f"{ticket_id} never reached {step}: {body}")


async def test_post_starts_workflow_and_returns_ids(api) -> None:
    http, recorder = api
    ticket = new_ticket()
    response = await http.post("/tickets", json=ticket)

    assert response.status_code == 202
    assert response.json() == {
        "ticket_id": ticket["ticket_id"],
        "workflow_id": f"ticket-{ticket['ticket_id']}",
        "duplicate": False,
    }
    assert response.headers["location"] == f"/tickets/{ticket['ticket_id']}"
    # Let it finish: a workflow left running on a stopped task queue would block time
    # skipping for every later test in the shared test server.
    await wait_for(http, ticket["ticket_id"], "completed")


async def test_duplicate_post_while_running_and_after_completion(api) -> None:
    http, recorder = api
    ticket = new_ticket("refund")  # stays running while it waits for approval
    first = await http.post("/tickets", json=ticket)
    await wait_for(http, ticket["ticket_id"], "awaiting_approval")

    second = await http.post("/tickets", json={**ticket, "body": "different body"})
    assert second.status_code == 200
    assert second.json() == {**first.json(), "duplicate": True}
    assert second.headers["location"] == first.headers["location"]

    approve = {"approved": True, "reviewer": "lead"}
    assert (
        await http.post(f"/tickets/{ticket['ticket_id']}/approval", json=approve)
    ).status_code == 202
    await wait_for(http, ticket["ticket_id"], "completed")

    third = await http.post("/tickets", json=ticket)
    assert third.status_code == 200
    assert third.json()["duplicate"] is True
    assert recorder.decided.count(ticket["ticket_id"]) == 1  # one execution only
    assert len(recorder.executed) == 1


async def test_get_returns_status_shape(api) -> None:
    http, _ = api
    ticket = new_ticket()
    await http.post("/tickets", json=ticket)
    body = await wait_for(http, ticket["ticket_id"], "completed")

    assert set(body) == {
        "ticket_id",
        "workflow_id",
        "step",
        "proposed_decision",
        "decision",
        "validation_errors",
        "approval",
        "result",
        "failure_reason",
        "updated_at",
    }
    assert body["decision"]["action"]["kind"] == "reply"
    assert body["result"]["idempotency_key"] == f"ticket-{ticket['ticket_id']}:reply"


async def test_approval_on_ticket_not_waiting_is_409(api) -> None:
    http, recorder = api
    ticket = new_ticket()
    await http.post("/tickets", json=ticket)
    await wait_for(http, ticket["ticket_id"], "completed")

    response = await http.post(
        f"/tickets/{ticket['ticket_id']}/approval", json={"approved": True, "reviewer": "x"}
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "ticket is not awaiting approval", "step": "completed"}
    assert [r.action.kind for r in recorder.executed] == ["reply"]


async def test_approval_on_waiting_refund_then_completed_with_refund(api) -> None:
    http, recorder = api
    ticket = new_ticket("refund")
    await http.post("/tickets", json=ticket)
    await wait_for(http, ticket["ticket_id"], "awaiting_approval")

    response = await http.post(
        f"/tickets/{ticket['ticket_id']}/approval",
        json={"approved": True, "reviewer": "billing-lead", "comment": "duplicate charge"},
    )
    assert response.status_code == 202
    assert response.json() == {
        "ticket_id": ticket["ticket_id"],
        "workflow_id": f"ticket-{ticket['ticket_id']}",
        "approved": True,
    }
    body = await wait_for(http, ticket["ticket_id"], "completed")
    assert body["result"]["kind"] == "refund"
    assert body["approval"]["reviewer"] == "billing-lead"
    assert [r.action.kind for r in recorder.executed] == ["refund"]


async def test_unknown_ticket_is_404(api) -> None:
    http, _ = api
    assert (await http.get("/tickets/T-does-not-exist")).status_code == 404
    response = await http.post(
        "/tickets/T-does-not-exist/approval", json={"approved": True, "reviewer": "x"}
    )
    assert response.status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"ticket_id": "T 1", "customer_id": "C-101", "subject": "s", "body": "b"},
        {"ticket_id": "T-1", "customer_id": "C-101", "subject": "s"},
        {"ticket_id": "T-1", "customer_id": "C-101", "subject": "s", "body": "b" * 5001},
    ],
    ids=["bad-id", "missing-body", "body-too-long"],
)
async def test_invalid_body_is_422(api, body) -> None:
    http, _ = api
    assert (await http.post("/tickets", json=body)).status_code == 422


async def test_invalid_approval_and_path_are_422(api) -> None:
    http, _ = api
    assert (await http.get("/tickets/bad id")).status_code == 422
    response = await http.post("/tickets/T-1/approval", json={"approved": True, "reviewer": ""})
    assert response.status_code == 422


class UnreachableClient:
    """A Temporal client whose every call fails as when the server is down."""

    def __init__(self, error: Exception, *, healthy: bool = True) -> None:
        self.error = error
        self.service_client = self.HealthService(healthy)

    class HealthService:
        def __init__(self, healthy: bool) -> None:
            self.healthy = healthy

        async def check_health(self, **kwargs) -> bool:
            if not self.healthy:
                raise RPCError("dns error", RPCStatusCode.UNAVAILABLE, b"")
            return True

    async def start_workflow(self, *args, **kwargs):
        raise self.error

    def get_workflow_handle(self, workflow_id: str):
        error = self.error

        class Handle:
            id = workflow_id

            async def query(self, *args, **kwargs):
                raise error

        return Handle()


@pytest.mark.parametrize(
    ("status", "healthy", "detail"),
    [
        (RPCStatusCode.UNAVAILABLE, False, "workflow service unavailable"),
        (RPCStatusCode.FAILED_PRECONDITION, True, "no worker available to answer"),
        (RPCStatusCode.DEADLINE_EXCEEDED, True, "no worker available to answer"),
        (RPCStatusCode.CANCELLED, True, "no worker available to answer"),
        (RPCStatusCode.DEADLINE_EXCEEDED, False, "workflow service unavailable"),
        (RPCStatusCode.CANCELLED, False, "workflow service unavailable"),
    ],
    ids=[
        "rpc-unavailable",
        "no-worker-precondition",
        "no-worker-deadline",
        "no-worker-timeout",
        "deadline-server-down",
        "timeout-server-down",
    ],
)
async def test_temporal_failures_on_query_are_503(status, healthy, detail) -> None:
    error = RPCError("query failed", status, b"")
    app = create_app(client=UnreachableClient(error, healthy=healthy), settings=Settings())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        get = await http.get("/tickets/T-1")
    assert (get.status_code, get.json()) == (503, {"detail": detail})


async def test_start_rpc_unavailable_is_503() -> None:
    error = RPCError("unavailable", RPCStatusCode.UNAVAILABLE, b"")
    app = create_app(client=UnreachableClient(error), settings=Settings())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        post = await http.post("/tickets", json=new_ticket())
    assert (post.status_code, post.json()) == (503, {"detail": "workflow service unavailable"})


async def test_temporal_connect_failure_is_503_and_retried(monkeypatch) -> None:
    attempts: list[str] = []

    async def refuse(address, **kwargs):
        attempts.append(address)
        raise RuntimeError("connection refused")

    monkeypatch.setattr("app.api.main.Client.connect", refuse)
    settings = Settings.model_validate({"temporal_address": "temporal.invalid:7233"})
    app = create_app(client=None, settings=settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        get = await http.get("/tickets/T-1")
        post = await http.post("/tickets", json=new_ticket())
    for response in (get, post):
        assert (response.status_code, response.json()) == (
            503,
            {"detail": "workflow service unavailable"},
        )
    assert attempts == ["temporal.invalid:7233"] * 2  # no client cached after a failure


def test_production_app_configures_json_logging_at_creation() -> None:
    import logging

    from app.logging import JsonFormatter

    root = logging.getLogger()
    previous_handlers, previous_level = root.handlers[:], root.level
    try:
        create_app(settings=Settings())
        assert any(isinstance(h.formatter, JsonFormatter) for h in root.handlers)
        assert logging.getLogger("uvicorn.error").propagate
    finally:
        root.handlers, root.level = previous_handlers, previous_level


class RacingClient:
    """The status query says "awaiting_approval", then the workflow closes before the signal."""

    def __init__(self) -> None:
        self.steps = ["awaiting_approval", "completed"]

    def get_workflow_handle(self, workflow_id: str):
        client = self

        class Handle:
            async def query(self, *args, **kwargs):
                from app.domain.models import WorkflowStatus

                step = client.steps.pop(0)
                return WorkflowStatus(ticket_id="T-1", workflow_id=workflow_id, step=step)

            async def signal(self, *args, **kwargs):
                raise RPCError("workflow execution already completed", RPCStatusCode.NOT_FOUND, b"")

        return Handle()


async def test_approval_racing_with_workflow_completion_is_409() -> None:
    app = create_app(client=RacingClient(), settings=Settings())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        response = await http.post(
            "/tickets/T-1/approval", json={"approved": True, "reviewer": "x"}
        )
    assert response.status_code == 409
    assert response.json() == {"detail": "ticket is not awaiting approval", "step": "completed"}


@pytest.mark.parametrize(
    "error",
    [WorkflowQueryFailedError("workflow task failing"), WorkflowQueryRejectedError(None)],
    ids=["failed", "rejected"],
)
async def test_query_failures_are_503(error, caplog) -> None:
    app = create_app(client=UnreachableClient(error), settings=Settings())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        response = await http.get("/tickets/T-1")
    assert response.status_code == 503
    assert response.json() == {"detail": "ticket state cannot be read right now"}
    record = next(r for r in caplog.records if r.getMessage() == "workflow_query_failed")
    assert record.workflow_id == "ticket-T-1"


@pytest.fixture
def api_log_lines():
    """JSON lines of the ``app.api`` logger, formatted at emit time as in production."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("app.api")
    previous_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        yield lambda: [json.loads(line) for line in stream.getvalue().splitlines()]
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)


async def test_every_api_line_for_a_ticket_request_has_both_ids(api, api_log_lines) -> None:
    http, _ = api
    ticket = new_ticket()
    ticket_id, workflow_id = ticket["ticket_id"], f"ticket-{ticket['ticket_id']}"
    requests = [
        (await http.post("/tickets", json=ticket)).status_code,
        (await http.post("/tickets", json={**ticket, "body": None})).status_code,
    ]
    await wait_for(http, ticket_id, "completed")
    requests += [
        (await http.post("/tickets", json=ticket)).status_code,
        (await http.get(f"/tickets/{ticket_id}")).status_code,
        (
            await http.post(
                f"/tickets/{ticket_id}/approval", json={"approved": True, "reviewer": "x"}
            )
        ).status_code,
    ]
    assert requests == [202, 422, 200, 200, 409]

    lines = api_log_lines()
    assert {line["event"] for line in lines} >= {
        "ticket_received",
        "workflow_started",
        "duplicate_ticket_submission",
        "approval_rejected_not_waiting",
        "http_request",
    }
    for line in lines:
        assert (line["ticket_id"], line["workflow_id"]) == (ticket_id, workflow_id), line
    http_lines = [line for line in lines if line["event"] == "http_request"]
    assert [(line["method"], line["path"], line["status"]) for line in http_lines[:2]] == [
        ("POST", "/tickets", 202),
        ("POST", "/tickets", 422),
    ]
    assert [(line["method"], line["status"]) for line in http_lines[-3:]] == [
        ("POST", 200),
        ("GET", 200),
        ("POST", 409),
    ]
    assert all(isinstance(line["duration_ms"], float) for line in http_lines)


async def test_failure_lines_carry_the_ticket_ids(monkeypatch, api_log_lines) -> None:
    async def refuse(address, **kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr("app.api.main.Client.connect", refuse)
    app = create_app(client=None, settings=Settings())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        await http.get("/tickets/T-9")
    lines = api_log_lines()
    assert [(line["event"], line.get("status")) for line in lines] == [
        ("temporal_connect_failed", None),
        ("http_request", 503),
    ]
    assert all((line["ticket_id"], line["workflow_id"]) == ("T-9", "ticket-T-9") for line in lines)


async def test_non_ticket_routes_are_not_logged(api, api_log_lines) -> None:
    http, _ = api
    assert (await http.get("/openapi.json")).status_code == 200
    assert api_log_lines() == []


@pytest.mark.parametrize(
    ("method", "path", "body", "expected"),
    [
        ("GET", "/tickets/T-2", b"", "T-2"),
        ("POST", "/tickets/T-2/approval", b"{}", "T-2"),
        ("POST", "/tickets", b'{"ticket_id": "T-3"}', "T-3"),
        ("POST", "/tickets", b'{"ticket_id": "bad id"}', None),
        ("POST", "/tickets", b"not json", None),
        ("POST", "/tickets", b"[1]", None),
        ("GET", "/tickets/bad%20id", b"", None),
        ("GET", "/docs", b"", None),
    ],
)
def test_ticket_id_from_request(method, path, body, expected) -> None:
    assert ticket_id_from(method, path, body) == expected
