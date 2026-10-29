"""HTTP request and response models.

Requests reuse the domain models (``Ticket``, ``ApprovalInput``) and ``GET`` returns the
workflow's ``WorkflowStatus`` as is; only the API-specific envelopes live here.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.domain.models import WorkflowStep


class TicketAccepted(BaseModel):
    ticket_id: str
    workflow_id: str
    duplicate: bool


class ApprovalAccepted(BaseModel):
    ticket_id: str
    workflow_id: str
    approved: bool


class ErrorDetail(BaseModel):
    detail: str


class NotAwaitingApproval(BaseModel):
    detail: str
    step: WorkflowStep
