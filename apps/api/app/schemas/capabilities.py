"""Actor-scoped read models. Action names bind to the existing typed transition API."""

from datetime import date, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.domain.types import RequestStatus, RequestType
from app.domain.workflow import Action
from app.schemas.core import ReadSchema


class DisplayName(ReadSchema):
    id: UUID
    name: str


class ChoicePage(ReadSchema):
    items: list[DisplayName] = Field(default_factory=list)
    limit: int
    offset: int
    has_more: bool = False


class ActionCapability(ReadSchema):
    action: Action
    approval_id: UUID | None = None
    revision_id: UUID | None = None
    reversal_request_id: UUID | None = None
    resolution_id: UUID | None = None


class ActionBlock(ReadSchema):
    action: Action
    code: Literal["not_ready", "reversal_review"]
    message: str


class RequestCapabilities(ReadSchema):
    request_id: UUID
    expected_version: int
    evaluated_at: datetime
    organization_timezone: str
    available_actions: list[ActionCapability]
    blocking: list[ActionBlock] = Field(default_factory=list)
    department: DisplayName
    participants: list[DisplayName]
    assignee_choices: ChoicePage | None = None


class CreationOptions(ReadSchema):
    organization_timezone: str
    request_types: list[RequestType]
    departments: ChoicePage


class QueueKind(StrEnum):
    APPROVALS = "approvals"
    REVERSALS = "reversals"
    SERVICE_WORK = "service_work"
    FINANCE_PROCESSING = "finance_processing"


class RequestSummary(ReadSchema):
    id: UUID
    type: RequestType
    title: str
    status: RequestStatus
    version: int
    requester: DisplayName
    department: DisplayName
    assigned_to: DisplayName | None = None
    created_at: datetime
    updated_at: datetime
    due_at: datetime | None
    amount: str | None = None
    currency: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    current_submission_sequence: int | None
    service_cycle_sequence: int | None
    available_actions: list[ActionCapability]
    blocking: list[ActionBlock] = Field(default_factory=list)


class WorkQueue(ReadSchema):
    queue: QueueKind
    organization_timezone: str
    evaluated_at: datetime
    items: list[RequestSummary]
    limit: int
    offset: int
    has_more: bool
