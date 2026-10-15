from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.domain.email import canonical_email
from app.domain.types import RequestStatus, RequestType, Role, UserStatus

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
DepartmentName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]
Description = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)
]


class InputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReadSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_validator("*", mode="after")
    @classmethod
    def utc_timestamps(cls, value: object) -> object:
        if isinstance(value, datetime):
            # PostgreSQL uses aware timestamps; the isolated SQLite adapter omits tzinfo.
            return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return value


class UserCreate(InputSchema):
    email: Annotated[str, StringConstraints(max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")]
    name: Name
    department_id: UUID | None = None
    roles: frozenset[Role] = Field(min_length=1)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("Invalid email identifier")
        return canonical_email(value)


class UserRead(ReadSchema):
    id: UUID
    organization_id: UUID
    email: str
    name: str
    department_id: UUID | None
    status: UserStatus
    created_at: datetime
    roles: frozenset[Role]


class DepartmentCreate(InputSchema):
    name: DepartmentName


class DepartmentRead(ReadSchema):
    id: UUID
    organization_id: UUID
    name: str


class RequestCreate(InputSchema):
    department_id: UUID
    type: RequestType
    title: Name
    raw_text: Description


class StatusHistoryRead(ReadSchema):
    id: UUID
    request_id: UUID
    sequence: int
    actor_id: UUID | None
    action: str
    from_state: RequestStatus | None
    to_state: RequestStatus
    reason: str
    at: datetime


class RequestRead(ReadSchema):
    id: UUID
    organization_id: UUID
    created_by: UUID
    department_id: UUID
    type: RequestType
    title: str
    raw_text: str
    status: RequestStatus
    version: int
    created_at: datetime
    updated_at: datetime


class DecisionRead(ReadSchema):
    id: UUID
    approval_id: UUID
    actor_id: UUID
    required_role: Role
    outcome: str
    reason: str
    at: datetime
    event_sequence: int


class StepRead(ReadSchema):
    id: UUID
    step: int
    approver_id: UUID | None
    approver_role: Role
    status: str
    candidates: list[UUID]
    decision: DecisionRead | None


class RevisionRead(ReadSchema):
    id: UUID
    predecessor_id: UUID | None
    change_sequence: int | None
    event_sequence: int
    actor_id: UUID
    at: datetime
    kind: str
    schema_version: int
    fields: dict[str, object]
    clarification: str


class SubmissionRead(ReadSchema):
    sequence: int
    routing_sequence: int
    revision_id: UUID
    policy_id: UUID
    policy_version: int
    policy_definition: dict[str, object]
    leave_overlap: bool
    approvals: list[StepRead] = Field(default_factory=list)


class ChangeRequestRead(ReadSchema):
    event_sequence: int
    submission_sequence: int
    approval_id: UUID
    actor_id: UUID
    required_role: Role


class RevisionPage(ReadSchema):
    items: list[RevisionRead]
    submissions: list[SubmissionRead]
    change_requests: list[ChangeRequestRead]
    limit: int
    offset: int


class ReversalRequestRead(ReadSchema):
    id: UUID
    request_id: UUID
    submission_sequence: int
    final_decision_id: UUID
    actor_id: UUID
    event_sequence: int
    intent: str
    organization_timezone: str


class ReversalDecisionRead(ReadSchema):
    id: UUID
    reversal_request_id: UUID
    actor_id: UUID
    event_sequence: int
    outcome: str
    organization_timezone: str


class ServiceResolutionRead(ReadSchema):
    id: UUID
    cycle_sequence: int
    event_sequence: int
    actor_id: UUID
    at: datetime
    body: str
    captured_by: UUID | None
    captured_at: datetime | None


class ServiceReopeningRead(ReadSchema):
    id: UUID
    resolution_id: UUID
    event_sequence: int
    policy_id: UUID
    expires_at: datetime


class ReversalPage(ReadSchema):
    items: list[ReversalRequestRead]
    limit: int
    offset: int


class LifecyclePage(ReadSchema):
    reversal_requests: list[ReversalRequestRead]
    reversal_decisions: list[ReversalDecisionRead]
    resolutions: list[ServiceResolutionRead]
    reopenings: list[ServiceReopeningRead]
    limit: int
    offset: int


class RequestDetail(RequestRead):
    due_at: datetime | None = None
    active_reversal: ReversalRequestRead | None = None
    reversal_decision: ReversalDecisionRead | None = None
    current_resolution: ServiceResolutionRead | None = None
    service_cycle_sequence: int | None = None
    replacement_request_id: UUID | None = None
    correction_source_id: UUID | None = None
    current_submission_sequence: int | None = None
    proposed_revision: RevisionRead | None = None
    correction: ChangeRequestRead | None = None
    assigned_to: UUID | None = None
    approved_at: datetime | None = None
    completed_at: datetime | None = None
    processed_by: UUID | None = None
    processing_reference: str | None = None
    resolution: str | None = None
    approval_policy_id: UUID | None = None
    structured_fields: dict[str, object] | None = None
    leave_overlap: bool = False
    approvals: list[StepRead] = Field(default_factory=list)
    status_history: list[StatusHistoryRead]


class RequestPage(BaseModel):
    items: list[RequestRead]
    limit: int
    offset: int


class Problem(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str
