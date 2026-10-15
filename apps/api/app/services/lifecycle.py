"""Explicit approval reversal and service work cycles; no external effects."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ActiveServiceReopenPolicy,
    Approval,
    ApprovalCandidate,
    ApprovalDecision,
    CorrectionLink,
    Organization,
    Request,
    RequestEvent,
    ReversalDecision,
    ReversalRequest,
    ServiceReopening,
    ServiceReopenPolicy,
    ServiceResolution,
    User,
)
from app.domain.identity import Principal
from app.domain.types import RequestStatus as S
from app.domain.types import RequestType as T
from app.domain.types import Role
from app.domain.workflow import Action, require_edge
from app.schemas.workflow import (
    ApproveReversal,
    CreateCorrection,
    RejectReversal,
    Reopen,
    RequestReversal,
    ServiceReopenPolicyDefinition,
)
from app.services.eligibility import active_roles, candidate_eligible, department_manager
from app.services.transition_service import (
    advance,
    capture_submission,
    conflict,
    current_sequence,
    forbid_unless,
    parse_fields,
    validated_steps,
)


def approval_source(session: Session, record: Request) -> tuple[Approval, ApprovalDecision]:
    steps = validated_steps(session, record)
    if not steps or any(step.status != "approved" for step in steps) or record.approved_at is None:
        raise conflict("A complete current approval is required.")
    final = steps[-1]
    decision = session.scalar(
        select(ApprovalDecision).where(
            ApprovalDecision.organization_id == record.organization_id,
            ApprovalDecision.approval_id == final.id,
        )
    )
    if decision is None or decision.at != record.approved_at:
        raise conflict("Final approval evidence is inconsistent.")
    return final, decision


def final_candidate(
    session: Session, actor: Principal, record: Request, final: Approval, *, lock: bool = True
) -> bool:
    candidate = session.get(ApprovalCandidate, (record.organization_id, final.id, actor.user_id))
    return candidate is not None and candidate_eligible(session, record, candidate, lock=lock)


def reversal_boundary(
    session: Session, record: Request, now: datetime, *, lock: bool = True
) -> str:
    if (
        record.type not in (T.EXPENSE, T.LEAVE)
        or record.completed_at is not None
        or record.processed_by is not None
        or record.processing_role is not None
        or record.processing_reference is not None
    ):
        raise conflict("Completed or processed requests cannot be reversed.")
    query = select(Organization).where(Organization.id == record.organization_id)
    organization = session.scalar(query.with_for_update(read=True) if lock else query)
    if organization is None:
        raise conflict("Organization configuration is unavailable.")
    if record.type == T.LEAVE:
        try:
            zone = ZoneInfo(organization.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise conflict("Organization timezone requires validation.") from None
        from app.db.models import RequestFields
        from app.schemas.workflow import LeaveSubmission

        fields = session.get(RequestFields, (record.organization_id, record.id))
        if fields is None:
            raise conflict("Submitted leave dates are unavailable.")
        data = parse_fields(record, fields.fields)
        assert isinstance(data, LeaveSubmission)
        if now.astimezone(zone).date() >= data.start_date:
            raise conflict("Leave reversal is permitted only before its start date.")
    return organization.timezone


def check_request_reversal(
    session: Session, actor: Principal, record: Request, now: datetime, *, lock: bool = True
) -> tuple[ApprovalDecision, str]:
    require_edge(record.type, record.status, Action.REQUEST_REVERSAL, S.REVERSAL_REVIEW)
    final, decision = approval_source(session, record)
    forbid_unless(
        actor.user_id == record.created_by
        or final_candidate(session, actor, record, final, lock=lock)
    )
    timezone = reversal_boundary(session, record, now, lock=lock)
    return decision, timezone


def request_reversal(
    session: Session, actor: Principal, record: Request, action: RequestReversal, now: datetime
) -> None:
    decision, timezone = check_request_reversal(session, actor, record, now)
    capture_submission(session, actor, record, now, approval=True)
    request = ReversalRequest(
        id=uuid4(),
        organization_id=record.organization_id,
        request_id=record.id,
        requester_id=record.created_by,
        submission_sequence=current_sequence(record),
        final_decision_id=decision.id,
        actor_id=actor.user_id,
        event_sequence=record.version + 1,
        intent=action.intent,
        organization_timezone=timezone,
    )
    session.add(request)
    record.active_reversal_id = request.id
    advance(session, actor, record, Action.REQUEST_REVERSAL, S.REVERSAL_REVIEW, action.reason, now)


def check_decide_reversal(
    session: Session,
    actor: Principal,
    record: Request,
    action: Action,
    reversal_request_id: UUID,
    now: datetime,
    *,
    lock: bool = True,
) -> tuple[ReversalRequest, str]:
    target = S.REVERSED if action == Action.APPROVE_REVERSAL else S.APPROVED
    require_edge(record.type, record.status, action, target)
    request = session.scalar(
        select(ReversalRequest).where(
            ReversalRequest.organization_id == record.organization_id,
            ReversalRequest.request_id == record.id,
            ReversalRequest.id == reversal_request_id,
        )
    )
    if (
        request is None
        or request.id != record.active_reversal_id
        or request.submission_sequence != current_sequence(record)
    ):
        raise conflict("Only the active reversal request can be decided.")
    final, decision = approval_source(session, record)
    if decision.id != request.final_decision_id:
        raise conflict("Reversal does not match the current approved submission.")
    # Independent review applies to acceptance and denial; no initiator may decide its own review.
    forbid_unless(
        actor.user_id != record.created_by
        and actor.user_id != request.actor_id
        and final_candidate(session, actor, record, final, lock=lock)
    )
    if (
        session.scalar(
            select(ReversalDecision.id).where(
                ReversalDecision.organization_id == record.organization_id,
                ReversalDecision.reversal_request_id == request.id,
            )
        )
        is not None
    ):
        raise conflict("Reversal was already decided.")
    if action == Action.APPROVE_REVERSAL:
        timezone = reversal_boundary(session, record, now, lock=lock)
    else:
        organization = session.get(Organization, record.organization_id)
        assert organization is not None
        timezone = organization.timezone
    return request, timezone


def decide_reversal(
    session: Session,
    actor: Principal,
    record: Request,
    action: ApproveReversal | RejectReversal,
    now: datetime,
) -> None:
    request, timezone = check_decide_reversal(
        session, actor, record, Action(action.action), action.reversal_request_id, now
    )
    target = S.REVERSED if isinstance(action, ApproveReversal) else S.APPROVED
    advance(session, actor, record, Action(action.action), target, action.reason, now)
    session.add(
        ReversalDecision(
            id=uuid4(),
            organization_id=record.organization_id,
            request_id=record.id,
            reversal_request_id=request.id,
            actor_id=actor.user_id,
            event_sequence=record.version,
            outcome="accepted" if isinstance(action, ApproveReversal) else "denied",
            organization_timezone=timezone,
        )
    )
    session.flush()


def check_create_correction(
    session: Session, actor: Principal, record: Request, reversal_request_id: UUID
) -> None:
    require_edge(record.type, record.status, Action.CREATE_CORRECTION, S.REVERSED)
    forbid_unless(actor.user_id == record.created_by)
    approval_source(session, record)
    reversal = session.scalar(
        select(ReversalRequest).where(
            ReversalRequest.organization_id == record.organization_id,
            ReversalRequest.request_id == record.id,
            ReversalRequest.id == reversal_request_id,
        )
    )
    decision = session.scalar(
        select(ReversalDecision).where(
            ReversalDecision.organization_id == record.organization_id,
            ReversalDecision.reversal_request_id == reversal_request_id,
            ReversalDecision.outcome == "accepted",
        )
    )
    if (
        reversal is None
        or decision is None
        or reversal.intent != "correct"
        or reversal.id != record.active_reversal_id
        or reversal.submission_sequence != current_sequence(record)
    ):
        raise conflict("An accepted correction reversal is required.")
    if session.get(CorrectionLink, (record.organization_id, record.id)) is not None:
        raise conflict("A replacement already exists.")


def create_correction(
    session: Session, actor: Principal, record: Request, action: CreateCorrection, now: datetime
) -> None:
    check_create_correction(session, actor, record, action.reversal_request_id)
    child = Request(
        id=uuid4(),
        organization_id=record.organization_id,
        created_by=record.created_by,
        department_id=record.department_id,
        type=record.type,
        title=record.title,
        raw_text=record.raw_text,
        due_at=record.due_at,
        follow_up_to_id=record.id,
        status=S.DRAFT,
        version=1,
        workflow_version=1,
        created_at=now,
        updated_at=now,
    )
    session.add(child)
    session.flush()
    session.add(
        RequestEvent(
            id=uuid4(),
            organization_id=record.organization_id,
            request_id=child.id,
            sequence=1,
            actor_id=actor.user_id,
            action="created",
            from_state=None,
            to_state=S.DRAFT,
            reason=action.reason,
            at=now,
        )
    )
    advance(session, actor, record, Action.CREATE_CORRECTION, S.REVERSED, action.reason, now)
    session.add(
        CorrectionLink(
            organization_id=record.organization_id,
            source_id=record.id,
            child_id=child.id,
            reversal_request_id=action.reversal_request_id,
            event_sequence=record.version,
        )
    )
    session.flush()


def valid_assignee(session: Session, record: Request, *, lock: bool = True) -> None:
    query = select(User).where(
        User.organization_id == record.organization_id,
        User.id == record.assigned_to,
        User.department_id == record.department_id,
        User.status == "active",
    )
    assignee = session.scalar(query.with_for_update(read=True) if lock else query)
    if assignee is None or not active_roles(
        session, Principal(record.organization_id, assignee.id), lock=lock
    ):
        raise conflict("The retained assignee is unavailable; reassignment is not permitted.")


def service_start(
    session: Session, actor: Principal, record: Request, reason: str, now: datetime
) -> None:
    forbid_unless(actor.user_id == record.assigned_to)
    if record.status == S.REOPENED:
        valid_assignee(session, record)
    if record.service_cycle_sequence is None and record.workflow_version == 1:
        record.service_cycle_sequence = record.version + 1
    advance(session, actor, record, Action.START, S.IN_PROGRESS, reason, now)


def service_resolve(
    session: Session, actor: Principal, record: Request, body: str, reason: str, now: datetime
) -> None:
    forbid_unless(actor.user_id == record.assigned_to)
    require_edge(record.type, record.status, Action.RESOLVE, S.RESOLVED)
    if record.workflow_version != 1:
        # Existing legacy service forward behavior is unchanged, but it cannot enter reopening.
        record.resolution = body
        advance(session, actor, record, Action.RESOLVE, S.RESOLVED, reason, now)
        return
    if record.service_cycle_sequence is None:
        started = session.scalar(
            select(RequestEvent)
            .where(
                RequestEvent.organization_id == record.organization_id,
                RequestEvent.request_id == record.id,
                RequestEvent.action == "start",
                RequestEvent.to_state == S.IN_PROGRESS,
            )
            .order_by(RequestEvent.sequence.desc())
        )
        if started is None or started.actor_id != record.assigned_to:
            raise conflict("Service work cycle requires trusted start evidence.")
        record.service_cycle_sequence = started.sequence
    resolution = ServiceResolution(
        id=uuid4(),
        organization_id=record.organization_id,
        request_id=record.id,
        cycle_sequence=record.service_cycle_sequence,
        event_sequence=record.version + 1,
        actor_id=actor.user_id,
        at=now,
        body=body,
    )
    if record.resolution is None:
        record.resolution = body
    record.latest_resolution_id = resolution.id
    advance(session, actor, record, Action.RESOLVE, S.RESOLVED, reason, now)
    session.add(resolution)
    session.flush()


@dataclass(frozen=True)
class ResolutionEvidence:
    id: UUID | None
    cycle_sequence: int
    event_sequence: int
    actor_id: UUID
    at: datetime
    body: str


def resolution_evidence(session: Session, record: Request) -> ResolutionEvidence:
    if (
        record.workflow_version != 1
        or record.status != S.RESOLVED
        or record.completed_at is not None
    ):
        raise conflict("A managed unresolved closure with trusted resolution is required.")
    if record.latest_resolution_id:
        existing = session.scalar(
            select(ServiceResolution).where(
                ServiceResolution.organization_id == record.organization_id,
                ServiceResolution.request_id == record.id,
                ServiceResolution.id == record.latest_resolution_id,
            )
        )
        if existing is None or existing.cycle_sequence != record.service_cycle_sequence:
            raise conflict("Current resolution evidence is inconsistent.")
        return ResolutionEvidence(
            existing.id,
            existing.cycle_sequence,
            existing.event_sequence,
            existing.actor_id,
            existing.at,
            existing.body,
        )
    resolved = session.scalar(
        select(RequestEvent).where(
            RequestEvent.organization_id == record.organization_id,
            RequestEvent.request_id == record.id,
            RequestEvent.sequence == record.version,
        )
    )
    started = session.scalar(
        select(RequestEvent)
        .where(
            RequestEvent.organization_id == record.organization_id,
            RequestEvent.request_id == record.id,
            RequestEvent.action == "start",
            RequestEvent.to_state == S.IN_PROGRESS,
        )
        .order_by(RequestEvent.sequence.desc())
    )
    if (
        resolved is None
        or started is None
        or resolved.actor_id is None
        or resolved.action != "resolve"
        or resolved.from_state != S.IN_PROGRESS
        or resolved.to_state != S.RESOLVED
        or resolved.actor_id != record.assigned_to
        or started.actor_id != record.assigned_to
        or started.sequence >= resolved.sequence
        or not record.resolution
        or not record.resolution.strip()
    ):
        raise conflict("Existing service resolution lacks trusted evidence; capture is blocked.")
    return ResolutionEvidence(
        None, started.sequence, resolved.sequence, resolved.actor_id, resolved.at, record.resolution
    )


def capture_resolution(
    session: Session, actor: Principal, record: Request, now: datetime
) -> ServiceResolution:
    evidence = resolution_evidence(session, record)
    if evidence.id is not None:
        existing = session.scalar(
            select(ServiceResolution).where(
                ServiceResolution.organization_id == record.organization_id,
                ServiceResolution.id == evidence.id,
            )
        )
        assert existing is not None
        return existing
    resolution = ServiceResolution(
        id=uuid4(),
        organization_id=record.organization_id,
        request_id=record.id,
        cycle_sequence=evidence.cycle_sequence,
        event_sequence=evidence.event_sequence,
        actor_id=evidence.actor_id,
        at=evidence.at,
        body=evidence.body,
        captured_by=actor.user_id,
        captured_at=now,
    )
    session.add(resolution)
    session.flush()
    return resolution


def check_reopen(
    session: Session,
    actor: Principal,
    record: Request,
    roles: frozenset[Role],
    now: datetime,
    *,
    resolution_id: UUID | None = None,
    lock: bool = True,
) -> tuple[ResolutionEvidence, ServiceReopenPolicy, datetime]:
    require_edge(record.type, record.status, Action.REOPEN, S.REOPENED)
    forbid_unless(
        actor.user_id == record.created_by
        or Role.ADMIN in roles
        or department_manager(session, actor, record.department_id, lock=lock)
    )
    valid_assignee(session, record, lock=lock)
    resolution = resolution_evidence(session, record)
    if resolution_id is not None and resolution_id != resolution.id:
        raise conflict("Reopening must reference the latest actual resolution.")
    query = select(ActiveServiceReopenPolicy).where(
        ActiveServiceReopenPolicy.organization_id == record.organization_id
    )
    selected = session.scalar(query.with_for_update(read=True) if lock else query)
    if selected is None:
        raise conflict("No service reopening policy is configured.")
    policy = session.scalar(
        select(ServiceReopenPolicy).where(
            ServiceReopenPolicy.organization_id == record.organization_id,
            ServiceReopenPolicy.id == selected.policy_id,
        )
    )
    if policy is None:
        raise conflict("Service reopening policy is unavailable.")
    try:
        definition = ServiceReopenPolicyDefinition.model_validate(policy.definition)
    except ValidationError:
        raise conflict("Service reopening policy requires validation.") from None
    resolved_at = (
        resolution.at.replace(tzinfo=UTC) if resolution.at.tzinfo is None else resolution.at
    )
    expires = resolved_at + timedelta(seconds=definition.window_seconds)
    if not resolved_at <= now <= expires:
        raise conflict("The service reopening window has expired.")
    return resolution, policy, expires


def reopen(
    session: Session,
    actor: Principal,
    record: Request,
    action: Reopen,
    roles: frozenset[Role],
    now: datetime,
) -> None:
    _, policy, expires = check_reopen(
        session, actor, record, roles, now, resolution_id=action.resolution_id
    )
    resolution = capture_resolution(session, actor, record, now)
    record.latest_resolution_id = resolution.id
    record.service_cycle_sequence = record.version + 1
    advance(session, actor, record, Action.REOPEN, S.REOPENED, action.reason, now)
    session.add(
        ServiceReopening(
            id=uuid4(),
            organization_id=record.organization_id,
            request_id=record.id,
            resolution_id=resolution.id,
            event_sequence=record.version,
            policy_id=policy.id,
            expires_at=expires,
        )
    )
    session.flush()
