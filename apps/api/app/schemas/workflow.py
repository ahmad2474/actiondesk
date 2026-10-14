"""Discriminated actions. Clients cannot supply policy, routing, or actor claims."""

import re
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, TypeAdapter, field_validator, model_validator

from app.domain.types import RequestStatus, Role
from app.schemas.core import Description, InputSchema, Name, ReadSchema, RequestDetail

Money = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=2)]


def decimal_string(value: object) -> Decimal:
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,16}(?:\.\d{1,2})?", value):
        raise ValueError("Money must be a decimal string with at most two fractional digits")
    return Decimal(value).quantize(Decimal("0.01"))


class ExpenseSubmission(InputSchema):
    type: Literal["expense"]
    vendor: Name
    amount: Money = Field(gt=0)
    currency: Literal["PKR"]
    purpose: Description

    @field_validator("amount", mode="before", json_schema_input_type=str)
    @classmethod
    def parse_amount(cls, value: object) -> Decimal:
        return decimal_string(value)


class LeaveSubmission(InputSchema):
    type: Literal["leave"]
    start_date: date
    end_date: date
    leave_type: Name

    @model_validator(mode="after")
    def ordered_dates(self) -> "LeaveSubmission":
        if self.end_date < self.start_date:
            raise ValueError("Leave dates must be ordered")
        return self


Submission = Annotated[ExpenseSubmission | LeaveSubmission, Field(discriminator="type")]


class TransitionBase(InputSchema):
    expected_version: int = Field(ge=1)
    reason: Description


class Submit(TransitionBase):
    action: Literal["submit"]
    data: Submission


class Triage(TransitionBase):
    action: Literal["triage"]


class Assign(TransitionBase):
    action: Literal["assign"]
    assignee_id: UUID


class Start(TransitionBase):
    action: Literal["start"]


class Resolve(TransitionBase):
    action: Literal["resolve"]
    resolution: Description


class Close(TransitionBase):
    action: Literal["close"]


class Approve(TransitionBase):
    action: Literal["approve"]
    approval_id: UUID


class Reject(TransitionBase):
    action: Literal["reject"]
    approval_id: UUID


class Process(TransitionBase):
    action: Literal["process"]
    reference: Name


class Cancel(TransitionBase):
    action: Literal["cancel"]


Transition = Annotated[
    Submit | Triage | Assign | Start | Resolve | Close | Approve | Reject | Process | Cancel,
    Field(discriminator="action"),
]
transition_adapter: TypeAdapter[Transition] = TypeAdapter(Transition)


class ApprovalPolicyDefinition(InputSchema):
    """Version 1 bounded policy: mandatory manager, optional finance above threshold."""

    schema_version: Literal[1]
    allow_department_fallback: bool
    currency: Literal["PKR"] | None = None
    finance_threshold: Money | None = None

    @field_validator("finance_threshold", mode="before")
    @classmethod
    def parse_threshold(cls, value: object) -> Decimal | None:
        return None if value is None else decimal_string(value)

    @model_validator(mode="after")
    def paired_threshold(self) -> "ApprovalPolicyDefinition":
        if (self.currency is None) != (self.finance_threshold is None):
            raise ValueError("Currency and finance threshold must be configured together")
        return self


class ApprovalRead(ReadSchema):
    id: UUID
    request_id: UUID
    step: int
    approver_role: Role
    status: str


class ApprovalPage(ReadSchema):
    items: list[ApprovalRead]
    limit: int
    offset: int


class TransitionOutcome(ReadSchema):
    request_id: UUID
    action: str
    version: int
    status: RequestStatus
    decision_id: UUID | None


class TransitionRead(ReadSchema):
    outcome: TransitionOutcome
    request: RequestDetail
