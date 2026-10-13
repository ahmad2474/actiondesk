"""Validation and loading of synthetic fixtures; not public request APIs."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, TypeAdapter, model_validator


class ServiceFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str
    location: str


class ExpenseFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vendor: str
    amount: Decimal = Field(gt=0)
    currency: Literal["PKR"]
    purpose: str


class LeaveFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_date: date
    end_date: date
    leave_type: Literal["annual"]

    @model_validator(mode="after")
    def valid_order(self) -> "LeaveFields":
        if self.end_date < self.start_date:
            raise ValueError("Synthetic leave end precedes start")
        return self


class SeedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    title: str
    raw_text: str
    created_at: AwareDatetime


class ServiceFixture(SeedRequest):
    type: Literal["service"]
    fields: ServiceFields


class ExpenseFixture(SeedRequest):
    type: Literal["expense"]
    fields: ExpenseFields


class LeaveFixture(SeedRequest):
    type: Literal["leave"]
    fields: LeaveFields


Fixture = Annotated[ServiceFixture | ExpenseFixture | LeaveFixture, Field(discriminator="type")]


def load_fixtures(count: Literal[10, 100] = 100) -> list[Fixture]:
    if count not in (10, 100):
        raise ValueError("Seed size must be 10 or 100")
    path = Path("data/seed/requests.json")
    records = TypeAdapter(list[Fixture]).validate_python(json.loads(path.read_text()))
    if len(records) != 100 or len({row.id for row in records}) != 100:
        raise ValueError("Canonical fixture set must contain 100 distinct IDs")
    return records[:count]
