"""Tenant-aware persistence shared by the API and future workflow services."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.domain.types import RequestStatus, RequestType, Role


class Base(DeclarativeBase):
    pass


ROLE = Enum(Role, name="role_enum", values_callable=lambda values: [v.value for v in values])
REQUEST_TYPE = Enum(
    RequestType, name="request_type_enum", values_callable=lambda v: [x.value for x in v]
)
REQUEST_STATUS = Enum(
    RequestStatus, name="request_status_enum", values_callable=lambda v: [x.value for x in v]
)


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    timezone: Mapped[str] = mapped_column(String(80), server_default="UTC")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TenantEntity:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"))


class Department(TenantEntity, Base):
    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "name"),
    )
    name: Mapped[str] = mapped_column(String(120))


class User(TenantEntity, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "email"),
        ForeignKeyConstraint(
            ["organization_id", "department_id"], ["departments.organization_id", "departments.id"]
        ),
        CheckConstraint("status IN ('active', 'inactive')", name="user_status"),
    )
    email: Mapped[str] = mapped_column(String(254))
    name: Mapped[str] = mapped_column(String(200))
    department_id: Mapped[UUID | None]
    password_hash: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), server_default="inactive")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RoleDefinition(Base):
    """Fixed role catalog; assignments remain separate and allow multiple roles."""

    __tablename__ = "roles"
    name: Mapped[Role] = mapped_column(ROLE, primary_key=True)


class RoleAssignment(Base):
    __tablename__ = "role_assignments"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "user_id"], ["users.organization_id", "users.id"]),
    )
    organization_id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(primary_key=True)
    role: Mapped[Role] = mapped_column(ROLE, ForeignKey("roles.name"), primary_key=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmployeeManager(Base):
    __tablename__ = "employee_managers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "employee_id"], ["users.organization_id", "users.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "manager_id", "manager_role"],
            [
                "role_assignments.organization_id",
                "role_assignments.user_id",
                "role_assignments.role",
            ],
        ),
        CheckConstraint("employee_id <> manager_id", name="manager_not_self"),
        CheckConstraint("manager_role = 'manager'", name="employee_manager_role"),
    )
    organization_id: Mapped[UUID] = mapped_column(primary_key=True)
    employee_id: Mapped[UUID] = mapped_column(primary_key=True)
    manager_id: Mapped[UUID]
    manager_role: Mapped[Role] = mapped_column(ROLE, server_default="manager")


class DepartmentManager(Base):
    __tablename__ = "department_managers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "department_id"], ["departments.organization_id", "departments.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "manager_id", "manager_role"],
            [
                "role_assignments.organization_id",
                "role_assignments.user_id",
                "role_assignments.role",
            ],
        ),
        CheckConstraint("manager_role = 'manager'", name="department_manager_role"),
    )
    organization_id: Mapped[UUID] = mapped_column(primary_key=True)
    department_id: Mapped[UUID] = mapped_column(primary_key=True)
    manager_id: Mapped[UUID] = mapped_column(primary_key=True)
    manager_role: Mapped[Role] = mapped_column(ROLE, server_default="manager")


class ApprovalPolicy(TenantEntity, Base):
    __tablename__ = "approval_policies"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "name", "version"),
        CheckConstraint("version > 0", name="positive_policy_version"),
    )
    name: Mapped[str] = mapped_column(String(120))
    version: Mapped[int] = mapped_column(Integer)
    request_type: Mapped[RequestType] = mapped_column(REQUEST_TYPE)
    definition: Mapped[dict[str, object]] = mapped_column(JSONB)


class Request(TenantEntity, Base):
    __tablename__ = "requests"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "id", "created_by"),
        UniqueConstraint(
            "organization_id", "created_by", "idempotency_key", name="uq_request_creation_key"
        ),
        ForeignKeyConstraint(
            ["organization_id", "created_by"], ["users.organization_id", "users.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "assigned_to"], ["users.organization_id", "users.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "department_id"], ["departments.organization_id", "departments.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "approval_policy_id"],
            ["approval_policies.organization_id", "approval_policies.id"],
        ),
        ForeignKeyConstraint(
            ["organization_id", "follow_up_to_id"], ["requests.organization_id", "requests.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "processed_by", "processing_role"],
            [
                "role_assignments.organization_id",
                "role_assignments.user_id",
                "role_assignments.role",
            ],
        ),
        CheckConstraint(
            "(processed_by IS NULL) = (processing_role IS NULL)", name="processing_actor_pair"
        ),
        CheckConstraint("processing_role = 'finance'", name="finance_processing_role"),
        CheckConstraint(
            "type <> 'expense' OR completed_at IS NULL OR processed_by IS NOT NULL",
            name="expense_completion_actor",
        ),
        CheckConstraint(
            "type <> 'expense' OR status <> 'COMPLETED' OR completed_at IS NOT NULL",
            name="expense_completion_timestamp",
        ),
        CheckConstraint("version > 0", name="positive_request_version"),
        CheckConstraint("follow_up_to_id <> id", name="follow_up_not_self"),
        CheckConstraint("priority IN ('low', 'normal', 'high', 'urgent')", name="request_priority"),
        Index("ix_requests_org_status_created", "organization_id", "status", "created_at"),
        Index("ix_requests_org_assignee_status", "organization_id", "assigned_to", "status"),
        Index("ix_requests_org_due", "organization_id", "due_at"),
    )
    type: Mapped[RequestType] = mapped_column(REQUEST_TYPE)
    title: Mapped[str] = mapped_column(String(200))
    raw_text: Mapped[str] = mapped_column(Text)
    status: Mapped[RequestStatus] = mapped_column(REQUEST_STATUS)
    priority: Mapped[str] = mapped_column(String(20), server_default="normal")
    created_by: Mapped[UUID]
    assigned_to: Mapped[UUID | None]
    department_id: Mapped[UUID]
    idempotency_key: Mapped[UUID | None]
    approval_policy_id: Mapped[UUID | None]
    follow_up_to_id: Mapped[UUID | None]
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_by: Mapped[UUID | None]
    processing_role: Mapped[Role | None] = mapped_column(ROLE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RequestFields(Base):
    __tablename__ = "request_fields"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "request_id"], ["requests.organization_id", "requests.id"]
        ),
        CheckConstraint("schema_version > 0", name="positive_fields_version"),
    )
    organization_id: Mapped[UUID] = mapped_column(primary_key=True)
    request_id: Mapped[UUID] = mapped_column(primary_key=True)
    schema_version: Mapped[int] = mapped_column(Integer, server_default="1")
    fields: Mapped[dict[str, object]] = mapped_column(JSONB)


class RequestEvent(TenantEntity, Base):
    __tablename__ = "request_events"
    __table_args__ = (
        UniqueConstraint("organization_id", "request_id", "sequence"),
        ForeignKeyConstraint(
            ["organization_id", "request_id"], ["requests.organization_id", "requests.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "actor_id"], ["users.organization_id", "users.id"]
        ),
        CheckConstraint("sequence > 0", name="positive_event_sequence"),
    )
    request_id: Mapped[UUID]
    sequence: Mapped[int] = mapped_column(Integer)
    actor_id: Mapped[UUID | None]
    action: Mapped[str] = mapped_column(String(80))
    from_state: Mapped[RequestStatus | None] = mapped_column(REQUEST_STATUS)
    to_state: Mapped[RequestStatus] = mapped_column(REQUEST_STATUS)
    reason: Mapped[str] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Approval(TenantEntity, Base):
    __tablename__ = "approvals"
    __table_args__ = (
        UniqueConstraint("organization_id", "request_id", "step"),
        ForeignKeyConstraint(
            ["organization_id", "request_id", "requester_id"],
            ["requests.organization_id", "requests.id", "requests.created_by"],
        ),
        ForeignKeyConstraint(
            ["organization_id", "approver_id", "approver_role"],
            [
                "role_assignments.organization_id",
                "role_assignments.user_id",
                "role_assignments.role",
            ],
        ),
        CheckConstraint("approver_id <> requester_id", name="no_self_approval"),
        CheckConstraint("step > 0", name="positive_approval_step"),
        CheckConstraint("approver_role IN ('manager', 'finance')", name="eligible_approval_role"),
        CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="approval_status"),
        Index("ix_approvals_org_approver_status", "organization_id", "approver_id", "status"),
    )
    request_id: Mapped[UUID]
    requester_id: Mapped[UUID]
    step: Mapped[int] = mapped_column(Integer)
    approver_id: Mapped[UUID]
    approver_role: Mapped[Role] = mapped_column(ROLE)
    status: Mapped[str] = mapped_column(String(20), server_default="pending")
    decision_reason: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OutboxEvent(TenantEntity, Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        UniqueConstraint("organization_id", "business_key"),
        ForeignKeyConstraint(
            ["organization_id", "request_id"], ["requests.organization_id", "requests.id"]
        ),
        CheckConstraint("attempt_count >= 0", name="nonnegative_outbox_attempts"),
        Index("ix_outbox_dispatched_created", "dispatched_at", "created_at"),
    )
    request_id: Mapped[UUID]
    business_key: Mapped[str] = mapped_column(String(200))
    event_type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, server_default="0")
