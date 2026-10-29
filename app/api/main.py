"""FastAPI application: thin handlers translating HTTP into Temporal start / query / signal.

Run with ``uvicorn app.api.main:app``. The Temporal client is created lazily in the
lifespan, so the API starts even while Temporal is down and answers ``503`` until it is back.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Path, Request, Response, status
from fastapi.responses import JSONResponse
from temporalio.client import Client, WorkflowHandle
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from app.api.schemas import ApprovalAccepted, ErrorDetail, NotAwaitingApproval, TicketAccepted
from app.config import Settings
from app.domain.models import (
    TICKET_ID_PATTERN,
    ApprovalInput,
    Ticket,
    WorkflowStatus,
    WorkflowStep,
)
from app.logging import configure_logging, ticket_extra, workflow_id_for
from app.workflows.ticket import TicketWorkflow

log = logging.getLogger("app.api")

QUERY_TIMEOUT = timedelta(seconds=10)
SERVICE_UNAVAILABLE = "workflow service unavailable"
NO_WORKER = "no worker available to answer"

TicketId = Annotated[str, Path(pattern=TICKET_ID_PATTERN)]


def create_app(client: Client | None = None, settings: Settings | None = None) -> FastAPI:
    """Build the app. Tests inject a client; in production the lifespan connects one."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if app.state.client is None:
            app.state.client = await Client.connect(
                app.state.settings.temporal_address,
                namespace=app.state.settings.temporal_namespace,
                data_converter=pydantic_data_converter,
                lazy=True,
            )
        yield

    app = FastAPI(title="Ticket workflow service", lifespan=lifespan)
    app.state.client = client
    app.state.settings = settings or Settings()
    if client is None:
        # At import time, so uvicorn's own startup lines are JSON too (the lifespan runs
        # after them).
        configure_logging(app.state.settings.log_level)
    _add_routes(app)
    return app


def get_client(request: Request) -> Client:
    return request.app.state.client


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


ClientDep = Annotated[Client, Depends(get_client)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

_UNAVAILABLE = {503: {"model": ErrorDetail}}


def _add_routes(app: FastAPI) -> None:
    @app.post(
        "/tickets",
        status_code=status.HTTP_202_ACCEPTED,
        response_model=TicketAccepted,
        responses={200: {"model": TicketAccepted}, **_UNAVAILABLE},
    )
    async def submit_ticket(
        ticket: Ticket, response: Response, client: ClientDep, settings: SettingsDep
    ) -> TicketAccepted:
        workflow_id = workflow_id_for(ticket.ticket_id)
        extra = ticket_extra(ticket.ticket_id, workflow_id)
        log.info(
            "ticket_received",
            extra={**extra, "subject_length": len(ticket.subject), "body_length": len(ticket.body)},
        )
        response.headers["Location"] = f"/tickets/{ticket.ticket_id}"
        try:
            await _temporal(
                client.start_workflow(
                    TicketWorkflow.run,
                    ticket,
                    id=workflow_id,
                    task_queue=settings.temporal_task_queue,
                    id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
                    id_conflict_policy=WorkflowIDConflictPolicy.FAIL,
                )
            )
        except WorkflowAlreadyStartedError:
            # Temporal guarantees one workflow per ID; the second body is ignored.
            log.info("duplicate_ticket_submission", extra=extra)
            response.status_code = status.HTTP_200_OK
            return TicketAccepted(
                ticket_id=ticket.ticket_id, workflow_id=workflow_id, duplicate=True
            )
        log.info("workflow_started", extra=extra)
        return TicketAccepted(ticket_id=ticket.ticket_id, workflow_id=workflow_id, duplicate=False)

    @app.get(
        "/tickets/{ticket_id}",
        response_model=WorkflowStatus,
        responses={404: {"model": ErrorDetail}, **_UNAVAILABLE},
    )
    async def get_ticket(ticket_id: TicketId, client: ClientDep) -> WorkflowStatus:
        return await _query_status(client.get_workflow_handle(workflow_id_for(ticket_id)))

    @app.post(
        "/tickets/{ticket_id}/approval",
        status_code=status.HTTP_202_ACCEPTED,
        response_model=ApprovalAccepted,
        responses={
            404: {"model": ErrorDetail},
            409: {"model": NotAwaitingApproval},
            **_UNAVAILABLE,
        },
    )
    async def submit_approval(
        ticket_id: TicketId, approval: ApprovalInput, client: ClientDep
    ) -> ApprovalAccepted | JSONResponse:
        workflow_id = workflow_id_for(ticket_id)
        extra = ticket_extra(ticket_id, workflow_id)
        handle = client.get_workflow_handle(workflow_id)
        current = await _query_status(handle)
        if current.step != WorkflowStep.AWAITING_APPROVAL:
            log.info("approval_rejected_not_waiting", extra={**extra, "step": current.step.value})
            body = NotAwaitingApproval(detail="ticket is not awaiting approval", step=current.step)
            return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=body.model_dump())
        # The workflow ignores an approval that arrives after it stopped waiting (see the
        # signal handler), so the query-then-signal race cannot trigger a late refund.
        await _temporal(handle.signal(TicketWorkflow.submit_approval, approval))
        log.info(
            "approval_sent",
            extra={**extra, "approved": approval.approved, "reviewer": approval.reviewer},
        )
        return ApprovalAccepted(
            ticket_id=ticket_id, workflow_id=workflow_id, approved=approval.approved
        )


async def _query_status(handle: WorkflowHandle) -> WorkflowStatus:
    return await _temporal(handle.query(TicketWorkflow.status, rpc_timeout=QUERY_TIMEOUT))


async def _temporal[T](call: Awaitable[T]) -> T:
    """Await a Temporal client call, mapping service failures to HTTP errors."""
    try:
        return await call
    except RPCError as err:
        if err.status == RPCStatusCode.NOT_FOUND:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "ticket not found") from err
        if err.status == RPCStatusCode.DEADLINE_EXCEEDED:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, NO_WORKER) from err
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, SERVICE_UNAVAILABLE) from err
    except RuntimeError as err:
        # A lazy client that cannot reach the server raises "Failed client connect".
        if "client connect" not in str(err):
            raise
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, SERVICE_UNAVAILABLE) from err


app = create_app()
