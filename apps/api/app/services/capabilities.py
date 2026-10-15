"""Consistent, read-only actor capabilities and narrowly scoped display data."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import ValidationError
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.db.models import (
    Approval,
    ApprovalCandidate,
    Department,
    Organization,
    Request,
    RequestEvent,
    RequestFields,
    User,
)
from app.domain.errors import DomainError
from app.domain.identity import Principal
from app.domain.types import RequestStatus as S
from app.domain.types import RequestType as T
from app.domain.types import Role
from app.domain.workflow import EDGES, Action
from app.schemas.capabilities import (
    ActionBlock,
    ActionCapability,
    ChoicePage,
    CreationOptions,
    DisplayName,
    QueueKind,
    RequestCapabilities,
    RequestSummary,
    WorkQueue,
)
from app.schemas.workflow import ExpenseSubmission, LeaveSubmission
from app.services.action_checks import check_action
from app.services.eligibility import active_roles, assignee_query, department_choices
from app.services.requests import validate_principal
from app.services.visibility import (
    actionable_approvals,
    current_approval,
    has_role,
    manages_department,
    processing_predicate,
    reversal_predicate,
    scoped_request,
    visible_predicate,
)


@contextmanager
def read_snapshot(session: Session) -> Iterator[None]:
    """New endpoint sessions only; PostgreSQL additionally enforces no business writes."""
    with session.begin(), session.no_autoflush:
        if session.get_bind().dialect.name == "postgresql":
            session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        yield


def observed_at(session: Session) -> datetime:
    if session.get_bind().dialect.name == "postgresql":
        value = session.scalar(select(func.clock_timestamp()))
        assert isinstance(value, datetime)
        return value
    return datetime.now(UTC)


def timezone(session: Session, actor: Principal) -> str:
    organization = session.get(Organization, actor.organization_id)
    if organization is None:
        raise DomainError(409, "Conflict", "Organization display context is unavailable.")
    try:
        ZoneInfo(organization.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise DomainError(
            409, "Conflict", "Organization display context requires validation."
        ) from None
    return organization.timezone


def department_name(session: Session, record: Request) -> DisplayName:
    department = session.scalar(
        select(Department).where(
            Department.organization_id == record.organization_id,
            Department.id == record.department_id,
        )
    )
    assert department is not None
    return DisplayName(id=department.id, name=department.name)


def participant_names(session: Session, record: Request) -> list[DisplayName]:
    # Only identities already disclosed by authorized request/history/current-plan reads.
    ids = {record.created_by}
    ids.update(value for value in (record.assigned_to, record.processed_by) if value is not None)
    ids.update(
        session.scalars(
            select(RequestEvent.actor_id).where(
                RequestEvent.organization_id == record.organization_id,
                RequestEvent.request_id == record.id,
                RequestEvent.actor_id.is_not(None),
            )
        )
    )
    ids.update(
        session.scalars(
            select(ApprovalCandidate.user_id)
            .join(
                Approval,
                (Approval.organization_id == ApprovalCandidate.organization_id)
                & (Approval.id == ApprovalCandidate.approval_id),
            )
            .join(
                Request,
                (Request.organization_id == Approval.organization_id)
                & (Request.id == Approval.request_id),
            )
            .where(
                current_approval(),
                ApprovalCandidate.organization_id == record.organization_id,
                ApprovalCandidate.request_id == record.id,
            )
        )
    )
    return [
        DisplayName(id=user.id, name=user.name)
        for user in session.scalars(
            select(User)
            .where(
                User.organization_id == record.organization_id,
                User.id.in_(ids),
            )
            .order_by(User.id)
        )
    ]


def actions_for(
    session: Session, actor: Principal, record: Request, now: datetime
) -> list[ActionCapability]:
    available = []
    for action in Action:
        if action == Action.ROUTE or (record.type, record.status, action) not in EDGES:
            continue
        try:
            available.append(check_action(session, actor, record, action, now))
        except DomainError as error:
            if error.status not in (403, 409, 422):
                raise
    return available


def explanations(
    session: Session, actor: Principal, record: Request, available: list[ActionCapability]
) -> list[ActionBlock]:
    # Do not echo validator errors: they may describe hidden policy/candidate state.
    if (
        record.type == T.EXPENSE
        and record.status == S.REVERSAL_REVIEW
        and actor.user_id != record.created_by
        and Role.FINANCE in active_roles(session, actor)
    ):
        return [
            ActionBlock(
                action=Action.PROCESS,
                code="reversal_review",
                message="Processing is on hold during reversal review.",
            )
        ]
    if record.created_by == actor.user_id and record.status in (S.DRAFT, S.NEEDS_INFO):
        action = Action.RESUBMIT if record.status == S.NEEDS_INFO else Action.SUBMIT
        if action not in {entry.action for entry in available}:
            return [
                ActionBlock(
                    action=action,
                    code="not_ready",
                    message="Submission is not ready. Save a valid revision if needed, "
                    "or ask for workflow configuration review.",
                )
            ]
    return []


def get_capabilities(
    session: Session, actor: Principal, request_id: UUID, limit: int = 50, offset: int = 0
) -> RequestCapabilities:
    with read_snapshot(session):
        validate_principal(session, actor)
        record = scoped_request(session, actor, request_id)
        now = observed_at(session)
        available = actions_for(session, actor, record, now)
        choices = None
        if Action.ASSIGN in {item.action for item in available}:
            users = list(
                session.scalars(
                    assignee_query(record)
                    .order_by(User.name, User.id)
                    .limit(limit + 1)
                    .offset(offset)
                )
            )
            choices = ChoicePage(
                items=[DisplayName(id=user.id, name=user.name) for user in users[:limit]],
                limit=limit,
                offset=offset,
                has_more=len(users) > limit,
            )
        return RequestCapabilities(
            request_id=record.id,
            expected_version=record.version,
            evaluated_at=now,
            organization_timezone=timezone(session, actor),
            available_actions=available,
            blocking=explanations(session, actor, record, available),
            department=department_name(session, record),
            participants=participant_names(session, record),
            assignee_choices=choices,
        )


def creation_options(
    session: Session, actor: Principal, limit: int = 50, offset: int = 0
) -> CreationOptions:
    with read_snapshot(session):
        validate_principal(session, actor)
        # Creation currently permits any existing department in the Principal's tenant.
        departments = list(
            session.scalars(
                department_choices(actor)
                .order_by(Department.name, Department.id)
                .limit(limit + 1)
                .offset(offset)
            )
        )
        return CreationOptions(
            organization_timezone=timezone(session, actor),
            request_types=list(T),
            departments=ChoicePage(
                items=[DisplayName(id=entry.id, name=entry.name) for entry in departments[:limit]],
                limit=limit,
                offset=offset,
                has_more=len(departments) > limit,
            ),
        )


def queue_predicate(actor: Principal, kind: QueueKind) -> ColumnElement[bool]:
    if kind == QueueKind.APPROVALS:
        return (
            select(Approval.id)
            .where(
                Approval.organization_id == Request.organization_id,
                Approval.request_id == Request.id,
                actionable_approvals(actor),
            )
            .correlate(Request)
            .exists()
        )
    if kind == QueueKind.REVERSALS:
        return reversal_predicate(actor)
    if kind == QueueKind.FINANCE_PROCESSING:
        return or_(
            processing_predicate(actor),
            (Request.type == T.EXPENSE)
            & (Request.status == S.REVERSAL_REVIEW)
            & (Request.created_by != actor.user_id)
            & has_role(actor, Role.FINANCE),
        )
    return (
        (Request.type == T.SERVICE)
        & Request.status.in_(
            [S.SUBMITTED, S.TRIAGED, S.ASSIGNED, S.IN_PROGRESS, S.RESOLVED, S.REOPENED]
        )
        & or_(
            Request.assigned_to == actor.user_id,
            manages_department(actor),
            has_role(actor, Role.ADMIN),
        )
    )


def queue_summary(
    session: Session, actor: Principal, record: Request, available: list[ActionCapability]
) -> RequestSummary:
    ids = {record.created_by, record.assigned_to}
    names = {
        user.id: DisplayName(id=user.id, name=user.name)
        for user in session.scalars(
            select(User).where(
                User.organization_id == record.organization_id,
                User.id.in_([value for value in ids if value is not None]),
            )
        )
    }
    summary = RequestSummary(
        id=record.id,
        type=record.type,
        title=record.title,
        status=record.status,
        version=record.version,
        requester=names[record.created_by],
        department=department_name(session, record),
        assigned_to=names.get(record.assigned_to) if record.assigned_to else None,
        created_at=record.created_at,
        updated_at=record.updated_at,
        due_at=record.due_at,
        current_submission_sequence=record.current_submission_sequence
        or record.submission_sequence,
        service_cycle_sequence=record.service_cycle_sequence,
        available_actions=available,
        blocking=explanations(session, actor, record, available),
    )
    fields = session.get(RequestFields, (record.organization_id, record.id))
    if fields:
        try:
            if record.type == T.EXPENSE:
                expense = ExpenseSubmission.model_validate(fields.fields)
                summary.amount, summary.currency = str(expense.amount), expense.currency
            elif record.type == T.LEAVE:
                leave = LeaveSubmission.model_validate(fields.fields)
                summary.start_date, summary.end_date = leave.start_date, leave.end_date
        except ValidationError:
            pass  # Legacy incomplete fields remain absent, never fabricated.
    return summary


def work_queue(
    session: Session, actor: Principal, kind: QueueKind, limit: int, offset: int
) -> WorkQueue:
    with read_snapshot(session):
        validate_principal(session, actor)
        now = observed_at(session)
        items = []
        eligible = 0
        query = (
            select(Request)
            .where(
                Request.organization_id == actor.organization_id,
                visible_predicate(actor),
                queue_predicate(actor, kind),
            )
            .order_by(Request.created_at, Request.id)
            .execution_options(yield_per=50)
        )
        for record in session.scalars(query):
            available = actions_for(session, actor, record, now)
            names = {item.action for item in available}
            if kind == QueueKind.APPROVALS and not names.intersection(
                {Action.APPROVE, Action.REJECT, Action.REQUEST_CHANGES}
            ):
                continue
            if kind == QueueKind.REVERSALS and not names.intersection(
                {Action.APPROVE_REVERSAL, Action.REJECT_REVERSAL}
            ):
                continue
            if (
                kind == QueueKind.FINANCE_PROCESSING
                and record.status != S.REVERSAL_REVIEW
                and Action.PROCESS not in names
            ):
                continue
            # Full shared evidence/eligibility checks occur before effective pagination.
            eligible += 1
            if eligible <= offset:
                continue
            items.append(queue_summary(session, actor, record, available))
            if len(items) > limit:
                break
        return WorkQueue(
            queue=kind,
            organization_timezone=timezone(session, actor),
            evaluated_at=now,
            items=items[:limit],
            limit=limit,
            offset=offset,
            has_more=len(items) > limit,
        )
