"""Requester-owned creation and reads. No transitions, routing or queue dispatch."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import Department, Request, RequestEvent, RoleAssignment, User
from app.domain.errors import DomainError
from app.domain.identity import Principal
from app.domain.types import UserStatus, initial_request_status
from app.schemas.core import (
    RequestCreate,
    RequestDetail,
    RequestPage,
    RequestRead,
    StatusHistoryRead,
)


def validate_principal(session: Session, principal: Principal) -> None:
    user = session.scalar(
        select(User).where(
            User.organization_id == principal.organization_id,
            User.id == principal.user_id,
            User.status == UserStatus.ACTIVE,
        )
    )
    if user is None:
        raise DomainError(401, "Unauthorized", "The authenticated user is unavailable.")
    role = session.scalar(
        select(RoleAssignment.role)
        .where(
            RoleAssignment.organization_id == principal.organization_id,
            RoleAssignment.user_id == principal.user_id,
            RoleAssignment.revoked_at.is_(None),
            RoleAssignment.granted_at <= datetime.now(UTC),
        )
        .limit(1)
    )
    if role is None:
        raise DomainError(403, "Forbidden", "An active organization role is required.")


def owned_request(session: Session, principal: Principal, request_id: UUID) -> Request:
    record = session.scalar(
        select(Request).where(
            Request.organization_id == principal.organization_id,
            Request.created_by == principal.user_id,
            Request.id == request_id,
        )
    )
    if record is None:
        raise DomainError(404, "Not Found", "Request not found.")
    return record


def request_detail(session: Session, record: Request) -> RequestDetail:
    events = session.scalars(
        select(RequestEvent)
        .where(
            RequestEvent.organization_id == record.organization_id,
            RequestEvent.request_id == record.id,
        )
        .order_by(RequestEvent.sequence)
    )
    return RequestDetail(
        **RequestRead.model_validate(record).model_dump(),
        status_history=[StatusHistoryRead.model_validate(event) for event in events],
    )


def create_request(
    session: Session, principal: Principal, payload: RequestCreate, key: UUID
) -> RequestDetail:
    with session.begin():
        validate_principal(session, principal)
        department = session.scalar(
            select(Department.id).where(
                Department.organization_id == principal.organization_id,
                Department.id == payload.department_id,
            )
        )
        if department is None:
            raise DomainError(422, "Unprocessable Content", "Department is unavailable.")
        now = datetime.now(UTC)
        record = session.scalar(
            insert(Request)
            .values(
                id=uuid4(),
                organization_id=principal.organization_id,
                created_by=principal.user_id,
                department_id=payload.department_id,
                type=payload.type,
                title=payload.title,
                raw_text=payload.raw_text,
                status=initial_request_status(payload.type),
                version=1,
                idempotency_key=key,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    Request.organization_id,
                    Request.created_by,
                    Request.idempotency_key,
                ]
            )
            .returning(Request)
        )
        if record is None:
            record = session.scalar(
                select(Request).where(
                    Request.organization_id == principal.organization_id,
                    Request.created_by == principal.user_id,
                    Request.idempotency_key == key,
                )
            )
            if record is None:
                raise DomainError(409, "Conflict", "Creation retry could not be resolved.")
            if (record.department_id, record.type, record.title, record.raw_text) != (
                payload.department_id,
                payload.type,
                payload.title,
                payload.raw_text,
            ):
                raise DomainError(409, "Conflict", "Idempotency key was used for different input.")
        else:
            session.add(
                RequestEvent(
                    organization_id=principal.organization_id,
                    request_id=record.id,
                    sequence=1,
                    actor_id=principal.user_id,
                    action="created",
                    from_state=None,
                    to_state=record.status,
                    reason="Request created by requester",
                    at=now,
                )
            )
            session.flush()
        result = request_detail(session, record)
    return result


def get_request(session: Session, principal: Principal, request_id: UUID) -> RequestDetail:
    validate_principal(session, principal)
    return request_detail(session, owned_request(session, principal, request_id))


def list_requests(session: Session, principal: Principal, limit: int, offset: int) -> RequestPage:
    validate_principal(session, principal)
    records = session.scalars(
        select(Request)
        .where(
            Request.organization_id == principal.organization_id,
            Request.created_by == principal.user_id,
        )
        .order_by(Request.created_at.desc(), Request.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return RequestPage(
        items=[RequestRead.model_validate(record) for record in records], limit=limit, offset=offset
    )
