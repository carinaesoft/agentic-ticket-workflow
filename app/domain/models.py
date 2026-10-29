"""Domain models.

Plain Pydantic v2 models shared by every layer. Temporal serialises them with its Pydantic
data converter, so they double as workflow and activity payloads. Money is ``Decimal`` end
to end.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

TICKET_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


class Category(StrEnum):
    ACCOUNT = "account"
    BILLING = "billing"
    TECHNICAL = "technical"
    OTHER = "other"


class Priority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class ActionKind(StrEnum):
    REPLY = "reply"
    REFUND = "refund"
    ESCALATE = "escalate"
    CLOSE = "close"


class WorkflowStep(StrEnum):
    RECEIVED = "received"
    DECIDING = "deciding"
    VALIDATING = "validating"
    AWAITING_APPROVAL = "awaiting_approval"
    ACTING = "acting"
    COMPLETED = "completed"
    FAILED = "failed"


# --- Reference data -------------------------------------------------------------------


class Ticket(BaseModel):
    ticket_id: str = Field(pattern=TICKET_ID_PATTERN)
    customer_id: str = Field(min_length=1, max_length=64)
    subject: str = Field(max_length=200)
    body: str = Field(max_length=5000)


class Customer(BaseModel):
    customer_id: str
    name: str
    plan: str
    status: str


class Invoice(BaseModel):
    invoice_id: str
    customer_id: str
    month: str
    amount_eur: Decimal
    status: str


class KbArticle(BaseModel):
    article_id: str
    title: str
    text: str


# --- Actions and decisions ------------------------------------------------------------


class ReplyAction(BaseModel):
    kind: Literal["reply"] = "reply"
    message: str
    article_ids: list[str] = Field(default_factory=list)


class RefundAction(BaseModel):
    kind: Literal["refund"] = "refund"
    invoice_id: str
    amount_eur: Decimal


class EscalateAction(BaseModel):
    kind: Literal["escalate"] = "escalate"
    reason: str


class CloseAction(BaseModel):
    kind: Literal["close"] = "close"
    reason: str


Action = Annotated[
    ReplyAction | RefundAction | EscalateAction | CloseAction,
    Field(discriminator="kind"),
]


class ProposedAction(BaseModel):
    """The action as the model wrote it: a ``kind`` plus free fields, checked by the rules."""

    model_config = ConfigDict(extra="allow")

    kind: str


class ProposedDecision(BaseModel):
    """What the agent loop parses from the model. Only the shape is enforced here."""

    category: str
    priority: str
    action: ProposedAction


class Decision(BaseModel):
    """The typed, effective decision. Only the rules produce one from a proposal."""

    category: Category
    priority: Priority
    action: Action


class DecisionContext(BaseModel):
    """Reference-data snapshot the rules need, returned by the decide activity."""

    customer: Customer
    invoices: list[Invoice]
    kb_ids: list[str]


# --- Workflow I/O ---------------------------------------------------------------------


class ApprovalInput(BaseModel):
    approved: bool
    reviewer: str = Field(min_length=1, max_length=100)
    comment: str | None = Field(default=None, max_length=500)


class ActionResult(BaseModel):
    kind: ActionKind
    helpdesk_reference: str
    idempotency_key: str
    outcome_message: str


class WorkflowStatus(BaseModel):
    ticket_id: str
    workflow_id: str
    step: WorkflowStep = WorkflowStep.RECEIVED
    proposed_decision: ProposedDecision | None = None
    decision: Decision | None = None
    validation_errors: list[str] = Field(default_factory=list)
    approval: ApprovalInput | None = None
    result: ActionResult | None = None
    failure_reason: str | None = None
    updated_at: datetime | None = None
