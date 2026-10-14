from datetime import datetime
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


class RequestDetail(RequestRead):
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
