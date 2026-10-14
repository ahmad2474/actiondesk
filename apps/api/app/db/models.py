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
    false,
    func,
    text,
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
    email: Mapped[str] = mapped_column(String(254))
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "email"),
        ForeignKeyConstraint(
            ["organization_id", "department_id"], ["departments.organization_id", "departments.id"]
        ),
        CheckConstraint("status IN ('active', 'inactive')", name="user_status"),
        Index(
            "uq_users_org_email_canonical",
            "organization_id",
            func.lower(func.btrim(email)),
            unique=True,
        ),
    )
    name: Mapped[str] = mapped_column(String(200))
    department_id: Mapped[UUID | None]
    password_hash: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), server_default="inactive")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RoleDefinition(Base):
    """Fixed role catalog; assignments remain separate and allow multiple roles."""

    __tablename__ = "roles"
    name: Mapped[Role] = mapped_column(ROLE, primary_key=True)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "user_id"], ["users.organization_id", "users.id"]),
        CheckConstraint("expires_at > created_at", name="session_positive_lifetime"),
        CheckConstraint("last_seen_at >= created_at", name="session_seen_after_creation"),
        Index("ix_auth_sessions_org_user", "organization_id", "user_id"),
        Index("ix_auth_sessions_expiry", "expires_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    organization_id: Mapped[UUID]
    user_id: Mapped[UUID]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
        UniqueConstraint("organization_id", "id", "request_type"),
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
        ForeignKeyConstraint(
            ["organization_id", "id", "current_submission_sequence"],
            [
                "request_submissions.organization_id",
                "request_submissions.request_id",
                "request_submissions.sequence",
            ],
            name="fk_current_submission",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["organization_id", "id", "proposed_revision_id"],
            [
                "request_revisions.organization_id",
                "request_revisions.request_id",
                "request_revisions.id",
            ],
            name="fk_proposed_revision",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["organization_id", "id", "active_reversal_id"],
            [
                "request_reversal_requests.organization_id",
                "request_reversal_requests.request_id",
                "request_reversal_requests.id",
            ],
            name="fk_active_reversal",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["organization_id", "id", "latest_resolution_id"],
            [
                "service_resolutions.organization_id",
                "service_resolutions.request_id",
                "service_resolutions.id",
            ],
            name="fk_latest_resolution",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["organization_id", "id", "service_cycle_sequence"],
            [
                "request_events.organization_id",
                "request_events.request_id",
                "request_events.sequence",
            ],
            name="fk_service_cycle",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint("version > 0", name="positive_request_version"),
        CheckConstraint(
            "workflow_version IS NULL OR workflow_version = 1", name="workflow_version"
        ),
        CheckConstraint(
            "submission_sequence IS NULL OR submission_sequence > 1", name="submission_sequence"
        ),
        CheckConstraint("processed_by <> created_by", name="no_self_processing"),
        CheckConstraint("follow_up_to_id <> id", name="follow_up_not_self"),
        CheckConstraint("priority IN ('low', 'normal', 'high', 'urgent')", name="request_priority"),
        Index("ix_requests_org_status_created", "organization_id", "status", "created_at"),
        Index("ix_requests_org_assignee_status", "organization_id", "assigned_to", "status"),
        Index("ix_requests_org_due", "organization_id", "due_at"),
    )
    current_submission_sequence: Mapped[int | None] = mapped_column(Integer)
    active_reversal_id: Mapped[UUID | None]
    service_cycle_sequence: Mapped[int | None] = mapped_column(Integer)
    latest_resolution_id: Mapped[UUID | None]
    proposed_revision_id: Mapped[UUID | None]
    workflow_version: Mapped[int | None] = mapped_column(Integer)
    submission_sequence: Mapped[int | None] = mapped_column(Integer)
    leave_overlap: Mapped[bool] = mapped_column(server_default=false())
    processing_reference: Mapped[str | None] = mapped_column(String(200))
    resolution: Mapped[str | None] = mapped_column(Text)
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
    submission_sequence: Mapped[int | None] = mapped_column(Integer)
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "request_id",
            "submission_sequence",
            "step",
            name="uq_approval_submission_step",
        ),
        Index(
            "uq_approval_original_step",
            "organization_id",
            "request_id",
            "step",
            unique=True,
            postgresql_where=text("submission_sequence IS NULL"),
            sqlite_where=text("submission_sequence IS NULL"),
        ),
        ForeignKeyConstraint(
            ["organization_id", "request_id", "submission_sequence"],
            [
                "request_events.organization_id",
                "request_events.request_id",
                "request_events.sequence",
            ],
            deferrable=True,
            initially="DEFERRED",
        ),
        UniqueConstraint("organization_id", "id", "request_id", "requester_id", "approver_role"),
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
        ForeignKeyConstraint(
            ["organization_id", "request_id", "closed_event_sequence"],
            [
                "request_events.organization_id",
                "request_events.request_id",
                "request_events.sequence",
            ],
        ),
        CheckConstraint("approver_id <> requester_id", name="no_self_approval"),
        CheckConstraint("step > 0", name="positive_approval_step"),
        CheckConstraint("approver_role IN ('manager', 'finance')", name="eligible_approval_role"),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'cancelled')", name="approval_status"
        ),
        Index("ix_approvals_org_approver_status", "organization_id", "approver_id", "status"),
    )
    request_id: Mapped[UUID]
    requester_id: Mapped[UUID]
    step: Mapped[int] = mapped_column(Integer)
    approver_id: Mapped[UUID | None]
    approver_role: Mapped[Role] = mapped_column(ROLE)
    status: Mapped[str] = mapped_column(String(20), server_default="pending")
    closed_event_sequence: Mapped[int | None] = mapped_column(Integer)
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


class ActiveApprovalPolicy(Base):
    __tablename__ = "active_approval_policies"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "policy_id", "request_type"],
            [
                "approval_policies.organization_id",
                "approval_policies.id",
                "approval_policies.request_type",
            ],
        ),
        CheckConstraint("request_type IN ('expense', 'leave')", name="active_review_policy_type"),
    )
    organization_id: Mapped[UUID] = mapped_column(primary_key=True)
    request_type: Mapped[RequestType] = mapped_column(REQUEST_TYPE, primary_key=True)
    policy_id: Mapped[UUID]


class ApprovalCandidate(Base):
    __tablename__ = "approval_candidates"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "approval_id", "request_id", "requester_id", "required_role"],
            [
                "approvals.organization_id",
                "approvals.id",
                "approvals.request_id",
                "approvals.requester_id",
                "approvals.approver_role",
            ],
        ),
        ForeignKeyConstraint(["organization_id", "user_id"], ["users.organization_id", "users.id"]),
        CheckConstraint("user_id <> requester_id", name="candidate_not_requester"),
        CheckConstraint(
            "routing_source IN ('employee_manager', 'department_manager', 'finance')",
            name="candidate_routing_source",
        ),
        Index("ix_candidates_org_user", "organization_id", "user_id"),
    )
    organization_id: Mapped[UUID] = mapped_column(primary_key=True)
    approval_id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(primary_key=True)
    request_id: Mapped[UUID]
    requester_id: Mapped[UUID]
    required_role: Mapped[Role] = mapped_column(ROLE)
    routing_source: Mapped[str] = mapped_column(String(30))


class ApprovalDecision(TenantEntity, Base):
    __tablename__ = "approval_decisions"
    __table_args__ = (
        UniqueConstraint("organization_id", "approval_id"),
        UniqueConstraint("organization_id", "id"),
        ForeignKeyConstraint(
            ["organization_id", "approval_id", "request_id", "requester_id", "required_role"],
            [
                "approvals.organization_id",
                "approvals.id",
                "approvals.request_id",
                "approvals.requester_id",
                "approvals.approver_role",
            ],
        ),
        ForeignKeyConstraint(
            ["organization_id", "approval_id", "actor_id"],
            [
                "approval_candidates.organization_id",
                "approval_candidates.approval_id",
                "approval_candidates.user_id",
            ],
        ),
        ForeignKeyConstraint(
            ["organization_id", "request_id", "event_sequence"],
            [
                "request_events.organization_id",
                "request_events.request_id",
                "request_events.sequence",
            ],
        ),
        CheckConstraint("actor_id <> requester_id", name="decision_not_requester"),
        CheckConstraint("outcome IN ('approved', 'rejected')", name="decision_outcome"),
    )
    approval_id: Mapped[UUID]
    request_id: Mapped[UUID]
    requester_id: Mapped[UUID]
    actor_id: Mapped[UUID]
    required_role: Mapped[Role] = mapped_column(ROLE)
    outcome: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    event_sequence: Mapped[int] = mapped_column(Integer)


class MutationReceipt(Base):
    __tablename__ = "mutation_receipts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "actor_id"], ["users.organization_id", "users.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "request_id", "version"],
            [
                "request_events.organization_id",
                "request_events.request_id",
                "request_events.sequence",
            ],
        ),
        ForeignKeyConstraint(
            ["organization_id", "decision_id"],
            ["approval_decisions.organization_id", "approval_decisions.id"],
        ),
        ForeignKeyConstraint(
            ["organization_id", "related_request_id"], ["requests.organization_id", "requests.id"]
        ),
        CheckConstraint("length(payload_hash) = 64", name="receipt_hash_length"),
    )
    organization_id: Mapped[UUID] = mapped_column(primary_key=True)
    actor_id: Mapped[UUID] = mapped_column(primary_key=True)
    idempotency_key: Mapped[UUID] = mapped_column(primary_key=True)
    request_id: Mapped[UUID]
    action: Mapped[str] = mapped_column(String(80))
    payload_hash: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[RequestStatus] = mapped_column(REQUEST_STATUS)
    decision_id: Mapped[UUID | None]
    related_request_id: Mapped[UUID | None]


class RequestRevision(TenantEntity, Base):
    __tablename__ = "request_revisions"
    __table_args__ = (
        UniqueConstraint("organization_id", "request_id", "id"),
        UniqueConstraint("organization_id", "request_id", "event_sequence"),
        ForeignKeyConstraint(
            ["organization_id", "request_id"], ["requests.organization_id", "requests.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "actor_id"], ["users.organization_id", "users.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "request_id", "event_sequence"],
            [
                "request_events.organization_id",
                "request_events.request_id",
                "request_events.sequence",
            ],
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["organization_id", "request_id", "predecessor_id"],
            [
                "request_revisions.organization_id",
                "request_revisions.request_id",
                "request_revisions.id",
            ],
        ),
        ForeignKeyConstraint(
            ["organization_id", "request_id", "change_sequence"],
            [
                "request_change_requests.organization_id",
                "request_change_requests.request_id",
                "request_change_requests.event_sequence",
            ],
            use_alter=True,
            name="fk_revision_change",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "kind IN ('submitted', 'captured', 'proposed', 'approval_capture')",
            name="revision_kind",
        ),
        CheckConstraint("schema_version = 1", name="revision_schema"),
        CheckConstraint("length(clarification) <= 20000", name="revision_clarification_length"),
    )
    request_id: Mapped[UUID]
    predecessor_id: Mapped[UUID | None]
    change_sequence: Mapped[int | None]
    event_sequence: Mapped[int]
    actor_id: Mapped[UUID]
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    kind: Mapped[str] = mapped_column(String(20))
    schema_version: Mapped[int] = mapped_column(Integer)
    fields: Mapped[dict[str, object]] = mapped_column(JSONB)
    clarification: Mapped[str] = mapped_column(Text)


class RequestSubmission(Base):
    __tablename__ = "request_submissions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "request_id", "sequence"],
            [
                "request_events.organization_id",
                "request_events.request_id",
                "request_events.sequence",
            ],
        ),
        ForeignKeyConstraint(
            ["organization_id", "request_id", "routing_sequence"],
            [
                "request_events.organization_id",
                "request_events.request_id",
                "request_events.sequence",
            ],
        ),
        ForeignKeyConstraint(
            ["organization_id", "request_id", "revision_id"],
            [
                "request_revisions.organization_id",
                "request_revisions.request_id",
                "request_revisions.id",
            ],
        ),
        ForeignKeyConstraint(
            ["organization_id", "policy_id"],
            ["approval_policies.organization_id", "approval_policies.id"],
        ),
        CheckConstraint("routing_sequence = sequence + 1", name="submission_routing_sequence"),
    )
    organization_id: Mapped[UUID] = mapped_column(primary_key=True)
    request_id: Mapped[UUID] = mapped_column(primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    routing_sequence: Mapped[int] = mapped_column(Integer)
    revision_id: Mapped[UUID]
    policy_id: Mapped[UUID]
    leave_overlap: Mapped[bool]


class RequestChangeRequest(Base):
    __tablename__ = "request_change_requests"
    __table_args__ = (
        UniqueConstraint("organization_id", "request_id", "submission_sequence"),
        ForeignKeyConstraint(
            ["organization_id", "request_id", "event_sequence"],
            [
                "request_events.organization_id",
                "request_events.request_id",
                "request_events.sequence",
            ],
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["organization_id", "request_id", "submission_sequence"],
            [
                "request_submissions.organization_id",
                "request_submissions.request_id",
                "request_submissions.sequence",
            ],
        ),
        ForeignKeyConstraint(
            ["organization_id", "approval_id", "actor_id"],
            [
                "approval_candidates.organization_id",
                "approval_candidates.approval_id",
                "approval_candidates.user_id",
            ],
        ),
        ForeignKeyConstraint(
            ["organization_id", "approval_id", "request_id", "requester_id", "required_role"],
            [
                "approvals.organization_id",
                "approvals.id",
                "approvals.request_id",
                "approvals.requester_id",
                "approvals.approver_role",
            ],
        ),
        CheckConstraint("actor_id <> requester_id", name="correction_not_requester"),
    )
    organization_id: Mapped[UUID] = mapped_column(primary_key=True)
    request_id: Mapped[UUID] = mapped_column(primary_key=True)
    event_sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    submission_sequence: Mapped[int] = mapped_column(Integer)
    approval_id: Mapped[UUID]
    actor_id: Mapped[UUID]
    requester_id: Mapped[UUID]
    required_role: Mapped[Role] = mapped_column(ROLE)


class ReversalRequest(TenantEntity, Base):
    __tablename__ = "request_reversal_requests"
    __table_args__ = (
        UniqueConstraint("organization_id", "request_id", "id"),
        UniqueConstraint("organization_id", "request_id", "event_sequence"),
        ForeignKeyConstraint(
            ["organization_id", "request_id", "requester_id"],
            ["requests.organization_id", "requests.id", "requests.created_by"],
        ),
        ForeignKeyConstraint(
            ["organization_id", "request_id", "submission_sequence"],
            [
                "request_submissions.organization_id",
                "request_submissions.request_id",
                "request_submissions.sequence",
            ],
        ),
        ForeignKeyConstraint(
            ["organization_id", "request_id", "event_sequence"],
            [
                "request_events.organization_id",
                "request_events.request_id",
                "request_events.sequence",
            ],
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["organization_id", "actor_id"], ["users.organization_id", "users.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "final_decision_id"],
            ["approval_decisions.organization_id", "approval_decisions.id"],
        ),
        CheckConstraint("intent IN ('withdraw','correct')", name="reversal_intent"),
    )
    request_id: Mapped[UUID]
    requester_id: Mapped[UUID]
    submission_sequence: Mapped[int] = mapped_column(Integer)
    final_decision_id: Mapped[UUID]
    actor_id: Mapped[UUID]
    event_sequence: Mapped[int] = mapped_column(Integer)
    intent: Mapped[str] = mapped_column(String(20))
    organization_timezone: Mapped[str] = mapped_column(String(80))


class ReversalDecision(TenantEntity, Base):
    __tablename__ = "request_reversal_decisions"
    __table_args__ = (
        UniqueConstraint("organization_id", "reversal_request_id"),
        ForeignKeyConstraint(
            ["organization_id", "request_id", "reversal_request_id"],
            [
                "request_reversal_requests.organization_id",
                "request_reversal_requests.request_id",
                "request_reversal_requests.id",
            ],
        ),
        ForeignKeyConstraint(
            ["organization_id", "actor_id"], ["users.organization_id", "users.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "request_id", "event_sequence"],
            [
                "request_events.organization_id",
                "request_events.request_id",
                "request_events.sequence",
            ],
        ),
        CheckConstraint("outcome IN ('accepted','denied')", name="reversal_outcome"),
    )
    request_id: Mapped[UUID]
    reversal_request_id: Mapped[UUID]
    actor_id: Mapped[UUID]
    event_sequence: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(20))
    organization_timezone: Mapped[str] = mapped_column(String(80))


class CorrectionLink(Base):
    __tablename__ = "request_correction_links"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "source_id", "reversal_request_id"],
            [
                "request_reversal_requests.organization_id",
                "request_reversal_requests.request_id",
                "request_reversal_requests.id",
            ],
        ),
        ForeignKeyConstraint(
            ["organization_id", "child_id"], ["requests.organization_id", "requests.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "source_id", "event_sequence"],
            [
                "request_events.organization_id",
                "request_events.request_id",
                "request_events.sequence",
            ],
        ),
        UniqueConstraint("organization_id", "child_id"),
        CheckConstraint("child_id <> source_id", name="correction_not_self"),
    )
    organization_id: Mapped[UUID] = mapped_column(primary_key=True)
    source_id: Mapped[UUID] = mapped_column(primary_key=True)
    child_id: Mapped[UUID]
    reversal_request_id: Mapped[UUID]
    event_sequence: Mapped[int] = mapped_column(Integer)


class ServiceResolution(TenantEntity, Base):
    __tablename__ = "service_resolutions"
    __table_args__ = (
        UniqueConstraint("organization_id", "request_id", "id"),
        UniqueConstraint("organization_id", "request_id", "event_sequence"),
        UniqueConstraint("organization_id", "request_id", "cycle_sequence"),
        ForeignKeyConstraint(
            ["organization_id", "request_id", "event_sequence"],
            [
                "request_events.organization_id",
                "request_events.request_id",
                "request_events.sequence",
            ],
        ),
        ForeignKeyConstraint(
            ["organization_id", "request_id", "cycle_sequence"],
            [
                "request_events.organization_id",
                "request_events.request_id",
                "request_events.sequence",
            ],
        ),
        ForeignKeyConstraint(
            ["organization_id", "actor_id"], ["users.organization_id", "users.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "captured_by"], ["users.organization_id", "users.id"]
        ),
        CheckConstraint("length(btrim(body)) BETWEEN 1 AND 20000", name="resolution_body_length"),
        CheckConstraint(
            "(captured_at IS NULL) = (captured_by IS NULL)", name="resolution_capture_pair"
        ),
    )
    request_id: Mapped[UUID]
    cycle_sequence: Mapped[int] = mapped_column(Integer)
    event_sequence: Mapped[int] = mapped_column(Integer)
    actor_id: Mapped[UUID]
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    body: Mapped[str] = mapped_column(Text)
    captured_by: Mapped[UUID | None]
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ServiceReopenPolicy(TenantEntity, Base):
    __tablename__ = "service_reopen_policies"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "name", "version"),
        CheckConstraint("version > 0", name="positive_reopen_policy_version"),
    )
    name: Mapped[str] = mapped_column(String(120))
    version: Mapped[int] = mapped_column(Integer)
    definition: Mapped[dict[str, object]] = mapped_column(JSONB)


class ActiveServiceReopenPolicy(Base):
    __tablename__ = "active_service_reopen_policies"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "policy_id"],
            ["service_reopen_policies.organization_id", "service_reopen_policies.id"],
        ),
    )
    organization_id: Mapped[UUID] = mapped_column(primary_key=True)
    policy_id: Mapped[UUID]


class ServiceReopening(TenantEntity, Base):
    __tablename__ = "service_reopenings"
    __table_args__ = (
        UniqueConstraint("organization_id", "request_id", "event_sequence"),
        UniqueConstraint("organization_id", "resolution_id"),
        ForeignKeyConstraint(
            ["organization_id", "request_id", "resolution_id"],
            [
                "service_resolutions.organization_id",
                "service_resolutions.request_id",
                "service_resolutions.id",
            ],
        ),
        ForeignKeyConstraint(
            ["organization_id", "request_id", "event_sequence"],
            [
                "request_events.organization_id",
                "request_events.request_id",
                "request_events.sequence",
            ],
        ),
        ForeignKeyConstraint(
            ["organization_id", "policy_id"],
            ["service_reopen_policies.organization_id", "service_reopen_policies.id"],
        ),
    )
    request_id: Mapped[UUID]
    resolution_id: Mapped[UUID]
    event_sequence: Mapped[int] = mapped_column(Integer)
    policy_id: Mapped[UUID]
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
