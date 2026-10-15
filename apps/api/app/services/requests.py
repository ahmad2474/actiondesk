"""Authenticated creation and participant-scoped reads; no queue dispatch."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import (
    Approval,
    ApprovalCandidate,
    ApprovalDecision,
    ApprovalPolicy,
    CorrectionLink,
    Department,
    Request,
    RequestChangeRequest,
    RequestEvent,
    RequestFields,
    RequestRevision,
    RequestSubmission,
    ReversalDecision,
    ReversalRequest,
    RoleAssignment,
    ServiceReopening,
    ServiceResolution,
    User,
)
from app.domain.errors import DomainError
from app.domain.identity import Principal
from app.domain.types import UserStatus, initial_request_status
from app.schemas.core import (
    ChangeRequestRead,
    DecisionRead,
    LifecyclePage,
    RequestCreate,
    RequestDetail,
    RequestPage,
    RequestRead,
    ReversalDecisionRead,
    ReversalRequestRead,
    RevisionPage,
    RevisionRead,
    ServiceReopeningRead,
    ServiceResolutionRead,
    StatusHistoryRead,
    StepRead,
    SubmissionRead,
)
from app.services.eligibility import department_choices
from app.services.visibility import (
    WorkScope,
    current_approval,
    scope_predicate,
    scoped_request,
    visible_predicate,
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


def request_detail(
    session: Session, record: Request, actor: Principal | None = None
) -> RequestDetail:
    events = session.scalars(
        select(RequestEvent)
        .where(
            RequestEvent.organization_id == record.organization_id,
            RequestEvent.request_id == record.id,
        )
        .order_by(RequestEvent.sequence)
    )
    fields = session.get(RequestFields, (record.organization_id, record.id))
    approvals = approval_reads(session, record)
    proposed = (
        session.scalar(
            select(RequestRevision).where(
                RequestRevision.organization_id == record.organization_id,
                RequestRevision.request_id == record.id,
                RequestRevision.id == record.proposed_revision_id,
            )
        )
        if record.proposed_revision_id
        else None
    )
    change = (
        session.scalar(
            select(RequestChangeRequest).where(
                RequestChangeRequest.organization_id == record.organization_id,
                RequestChangeRequest.request_id == record.id,
                RequestChangeRequest.submission_sequence
                == (record.current_submission_sequence or record.submission_sequence),
            )
        )
        if record.status == "NEEDS_INFO"
        else None
    )
    reversal = (
        session.scalar(
            select(ReversalRequest).where(
                ReversalRequest.organization_id == record.organization_id,
                ReversalRequest.request_id == record.id,
                ReversalRequest.id == record.active_reversal_id,
            )
        )
        if record.active_reversal_id
        else None
    )
    reversal_decision = (
        session.scalar(
            select(ReversalDecision).where(
                ReversalDecision.organization_id == record.organization_id,
                ReversalDecision.reversal_request_id == record.active_reversal_id,
            )
        )
        if reversal
        else None
    )
    resolution = (
        session.scalar(
            select(ServiceResolution).where(
                ServiceResolution.organization_id == record.organization_id,
                ServiceResolution.request_id == record.id,
                ServiceResolution.id == record.latest_resolution_id,
                ServiceResolution.cycle_sequence == record.service_cycle_sequence,
            )
        )
        if record.latest_resolution_id
        else None
    )
    child = session.get(CorrectionLink, (record.organization_id, record.id))

    def visible_link(request_id: UUID | None) -> UUID | None:
        if request_id is None or actor is None:
            return None
        return session.scalar(
            select(Request.id).where(
                Request.organization_id == actor.organization_id,
                Request.id == request_id,
                visible_predicate(actor),
            )
        )

    return RequestDetail(
        due_at=record.due_at,
        active_reversal=ReversalRequestRead.model_validate(reversal) if reversal else None,
        reversal_decision=ReversalDecisionRead.model_validate(reversal_decision)
        if reversal_decision
        else None,
        current_resolution=ServiceResolutionRead.model_validate(resolution) if resolution else None,
        service_cycle_sequence=record.service_cycle_sequence,
        replacement_request_id=visible_link(child.child_id if child else None),
        correction_source_id=visible_link(record.follow_up_to_id),
        **RequestRead.model_validate(record).model_dump(),
        current_submission_sequence=record.current_submission_sequence
        or record.submission_sequence,
        proposed_revision=RevisionRead.model_validate(proposed) if proposed else None,
        correction=ChangeRequestRead.model_validate(change) if change else None,
        assigned_to=record.assigned_to,
        approved_at=record.approved_at,
        completed_at=record.completed_at,
        processed_by=record.processed_by,
        processing_reference=record.processing_reference,
        resolution=resolution.body
        if resolution
        else (record.resolution if record.service_cycle_sequence is None else None),
        approval_policy_id=record.approval_policy_id,
        structured_fields=fields.fields if fields else None,
        leave_overlap=record.leave_overlap,
        approvals=approvals,
        status_history=[StatusHistoryRead.model_validate(event) for event in events],
    )


def create_request(
    session: Session, principal: Principal, payload: RequestCreate, key: UUID
) -> RequestDetail:
    with session.begin():
        validate_principal(session, principal)
        department = session.scalar(
            department_choices(principal).where(Department.id == payload.department_id)
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
                workflow_version=1,
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
        result = request_detail(session, record, principal)
    return result


def get_request(session: Session, principal: Principal, request_id: UUID) -> RequestDetail:
    validate_principal(session, principal)
    return request_detail(session, scoped_request(session, principal, request_id), principal)


def list_requests(
    session: Session,
    principal: Principal,
    limit: int,
    offset: int,
    scope: WorkScope = WorkScope.MINE,
) -> RequestPage:
    validate_principal(session, principal)
    records = session.scalars(
        select(Request)
        .where(
            Request.organization_id == principal.organization_id,
            scope_predicate(principal, scope),
        )
        .order_by(Request.created_at.desc(), Request.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return RequestPage(
        items=[RequestRead.model_validate(record) for record in records], limit=limit, offset=offset
    )


def approval_reads(
    session: Session, record: Request, sequence: int | None = None
) -> list[StepRead]:
    steps = session.scalars(
        select(Approval)
        .join(
            Request,
            (Request.organization_id == Approval.organization_id)
            & (Request.id == Approval.request_id),
        )
        .where(
            Approval.organization_id == record.organization_id,
            Approval.request_id == record.id,
            current_approval()
            if sequence is None
            else (Approval.submission_sequence == sequence)
            | (
                (Approval.submission_sequence.is_(None)) & (Request.submission_sequence == sequence)
            ),
        )
        .order_by(Approval.step)
    )
    approvals = []
    for step in steps:
        candidates = list(
            session.scalars(
                select(ApprovalCandidate.user_id)
                .where(
                    ApprovalCandidate.organization_id == record.organization_id,
                    ApprovalCandidate.approval_id == step.id,
                )
                .order_by(ApprovalCandidate.user_id)
            )
        )
        decision = session.scalar(
            select(ApprovalDecision).where(
                ApprovalDecision.organization_id == record.organization_id,
                ApprovalDecision.approval_id == step.id,
            )
        )
        approvals.append(
            StepRead(
                id=step.id,
                step=step.step,
                approver_id=step.approver_id,
                approver_role=step.approver_role,
                status=step.status,
                candidates=candidates,
                decision=DecisionRead.model_validate(decision) if decision else None,
            )
        )
    return approvals


def list_revisions(
    session: Session, principal: Principal, request_id: UUID, limit: int, offset: int
) -> RevisionPage:
    validate_principal(session, principal)
    record = scoped_request(session, principal, request_id)
    revisions = list(
        session.scalars(
            select(RequestRevision)
            .where(
                RequestRevision.organization_id == record.organization_id,
                RequestRevision.request_id == record.id,
            )
            .order_by(RequestRevision.event_sequence)
            .limit(limit)
            .offset(offset)
        )
    )
    submissions = list(
        session.scalars(
            select(RequestSubmission)
            .where(
                RequestSubmission.organization_id == record.organization_id,
                RequestSubmission.request_id == record.id,
                RequestSubmission.revision_id.in_([revision.id for revision in revisions]),
            )
            .order_by(RequestSubmission.sequence)
        )
    )
    submission_reads = []
    for submission in submissions:
        policy = session.scalar(
            select(ApprovalPolicy).where(
                ApprovalPolicy.organization_id == record.organization_id,
                ApprovalPolicy.id == submission.policy_id,
            )
        )
        assert policy is not None
        submission_reads.append(
            SubmissionRead(
                sequence=submission.sequence,
                routing_sequence=submission.routing_sequence,
                revision_id=submission.revision_id,
                policy_id=policy.id,
                policy_version=policy.version,
                policy_definition=policy.definition,
                leave_overlap=submission.leave_overlap,
                approvals=approval_reads(session, record, submission.sequence),
            )
        )
    changes = session.scalars(
        select(RequestChangeRequest)
        .where(
            RequestChangeRequest.organization_id == record.organization_id,
            RequestChangeRequest.request_id == record.id,
            (
                RequestChangeRequest.event_sequence.in_(
                    [
                        revision.change_sequence
                        for revision in revisions
                        if revision.change_sequence is not None
                    ]
                )
            )
            | (
                RequestChangeRequest.submission_sequence.in_(
                    [submission.sequence for submission in submissions]
                )
            ),
        )
        .order_by(RequestChangeRequest.event_sequence)
    )
    return RevisionPage(
        items=[RevisionRead.model_validate(revision) for revision in revisions],
        submissions=submission_reads,
        change_requests=[ChangeRequestRead.model_validate(change) for change in changes],
        limit=limit,
        offset=offset,
    )


def list_lifecycle(
    session: Session, actor: Principal, request_id: UUID, limit: int, offset: int
) -> LifecyclePage:
    validate_principal(session, actor)
    record = scoped_request(session, actor, request_id)
    reversals = session.scalars(
        select(ReversalRequest)
        .where(
            ReversalRequest.organization_id == record.organization_id,
            ReversalRequest.request_id == record.id,
        )
        .order_by(ReversalRequest.event_sequence)
        .limit(limit)
        .offset(offset)
    )
    decisions = session.scalars(
        select(ReversalDecision)
        .where(
            ReversalDecision.organization_id == record.organization_id,
            ReversalDecision.request_id == record.id,
        )
        .order_by(ReversalDecision.event_sequence)
        .limit(limit)
        .offset(offset)
    )
    resolutions = session.scalars(
        select(ServiceResolution)
        .where(
            ServiceResolution.organization_id == record.organization_id,
            ServiceResolution.request_id == record.id,
        )
        .order_by(ServiceResolution.event_sequence)
        .limit(limit)
        .offset(offset)
    )
    reopenings = session.scalars(
        select(ServiceReopening)
        .where(
            ServiceReopening.organization_id == record.organization_id,
            ServiceReopening.request_id == record.id,
        )
        .order_by(ServiceReopening.event_sequence)
        .limit(limit)
        .offset(offset)
    )
    return LifecyclePage(
        reversal_requests=[ReversalRequestRead.model_validate(item) for item in reversals],
        reversal_decisions=[ReversalDecisionRead.model_validate(item) for item in decisions],
        resolutions=[ServiceResolutionRead.model_validate(item) for item in resolutions],
        reopenings=[ServiceReopeningRead.model_validate(item) for item in reopenings],
        limit=limit,
        offset=offset,
    )
