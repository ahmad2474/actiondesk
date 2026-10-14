"""One transactional entry point for manual workflows; never dispatches external effects."""

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.models import (
    Approval,
    ApprovalCandidate,
    ApprovalDecision,
    ApprovalPolicy,
    MutationReceipt,
    Request,
    RequestChangeRequest,
    RequestEvent,
    RequestFields,
    RequestRevision,
    RequestSubmission,
    User,
)
from app.domain.errors import DomainError
from app.domain.identity import Principal
from app.domain.types import RequestStatus as S
from app.domain.types import RequestType as T
from app.domain.types import Role
from app.domain.workflow import Action, require_edge
from app.schemas.workflow import (
    ApprovalPolicyDefinition,
    Approve,
    Assign,
    Cancel,
    Close,
    ExpenseSubmission,
    LeaveSubmission,
    Process,
    Reject,
    RequestChanges,
    Resolve,
    Resubmit,
    Revise,
    Start,
    Submit,
    Transition,
    TransitionOutcome,
    TransitionRead,
    Triage,
)
from app.services.eligibility import active_roles, candidate_eligible, department_manager
from app.services.policies import persist_plan, resolve_plan
from app.services.requests import request_detail, validate_principal
from app.services.visibility import current_approval, scoped_request


def conflict(detail: str) -> DomainError:
    return DomainError(409, "Conflict", detail)


def forbid_unless(condition: bool) -> None:
    if not condition:
        raise DomainError(403, "Forbidden", "The actor is not authorized for this action.")


def advance(
    session: Session,
    actor: Principal,
    record: Request,
    action: Action,
    target: S,
    reason: str,
    now: datetime,
) -> None:
    require_edge(record.type, record.status, action, target)
    old = record.status
    record.status = target
    record.version += 1
    record.updated_at = now
    session.add(
        RequestEvent(
            organization_id=record.organization_id,
            request_id=record.id,
            sequence=record.version,
            actor_id=actor.user_id,
            action=action.value,
            from_state=old,
            to_state=target,
            reason=reason,
            at=now,
        )
    )
    session.flush()  # Submission and routing are two real updates, not a skipped state.


def validated_steps(session: Session, record: Request) -> list[Approval]:
    """Never reinterpret legacy nominees or status strings as immutable decision evidence."""
    if record.workflow_version != 1 or record.submission_sequence is None:
        raise conflict("Legacy approval plan requires explicit validation; mutation is blocked.")
    policy = session.scalar(
        select(ApprovalPolicy).where(
            ApprovalPolicy.organization_id == record.organization_id,
            ApprovalPolicy.id == record.approval_policy_id,
            ApprovalPolicy.request_type == record.type,
        )
    )
    fields = session.get(RequestFields, (record.organization_id, record.id))
    if policy is None or fields is None or fields.schema_version != 1:
        raise conflict("Approval plan has incomplete submission evidence.")
    try:
        definition = ApprovalPolicyDefinition.model_validate(policy.definition)
        expected = [Role.MANAGER]
        if record.type == T.EXPENSE:
            data = ExpenseSubmission.model_validate(fields.fields)
            if definition.currency != data.currency or definition.finance_threshold is None:
                raise ValueError("Invalid expense policy")
            if data.amount > definition.finance_threshold:
                expected.append(Role.FINANCE)
        elif record.type == T.LEAVE:
            LeaveSubmission.model_validate(fields.fields)
            if definition.currency is not None:
                raise ValueError("Invalid leave policy")
        else:
            raise ValueError("Invalid request type")
    except (ValidationError, ValueError):
        raise conflict("Approval plan requires explicit validation.") from None
    sequence = record.current_submission_sequence or record.submission_sequence
    submitted = session.scalar(
        select(RequestEvent).where(
            RequestEvent.organization_id == record.organization_id,
            RequestEvent.request_id == record.id,
            RequestEvent.sequence == sequence,
        )
    )
    routed = session.scalar(
        select(RequestEvent).where(
            RequestEvent.organization_id == record.organization_id,
            RequestEvent.request_id == record.id,
            RequestEvent.sequence == sequence + 1,
        )
    )
    if (
        submitted is None
        or routed is None
        or submitted.actor_id != record.created_by
        or submitted.to_state != S.SUBMITTED
        or (submitted.action, submitted.from_state)
        not in {("submit", S.DRAFT), ("resubmit", S.NEEDS_INFO)}
        or routed.actor_id != record.created_by
        or routed.action != "route"
        or routed.from_state != S.SUBMITTED
        or routed.to_state != S.MANAGER_REVIEW
    ):
        raise conflict("Approval plan lacks trusted submission history.")
    binding = session.get(RequestSubmission, (record.organization_id, record.id, sequence))
    if binding is not None:
        snapshot = session.scalar(
            select(RequestRevision).where(
                RequestRevision.organization_id == record.organization_id,
                RequestRevision.request_id == record.id,
                RequestRevision.id == binding.revision_id,
            )
        )
        if (
            snapshot is None
            or snapshot.fields != fields.fields
            or binding.policy_id != policy.id
            or binding.leave_overlap != record.leave_overlap
        ):
            raise conflict("Submitted projection conflicts with immutable evidence.")
    elif record.current_submission_sequence is not None:
        raise conflict("Current submission binding is missing.")
    steps = list(
        session.scalars(
            select(Approval)
            .join(
                Request,
                (Request.organization_id == Approval.organization_id)
                & (Request.id == Approval.request_id),
            )
            .where(
                current_approval(),
                Approval.organization_id == record.organization_id,
                Approval.request_id == record.id,
            )
            .order_by(Approval.step)
        )
    )
    if [step.approver_role for step in steps] != expected or [step.step for step in steps] != list(
        range(1, len(expected) + 1)
    ):
        raise conflict("Approval plan does not match the submitted policy.")
    for step in steps:
        candidates = list(
            session.scalars(
                select(ApprovalCandidate).where(
                    ApprovalCandidate.organization_id == record.organization_id,
                    ApprovalCandidate.approval_id == step.id,
                )
            )
        )
        if any(
            candidate.request_id != record.id
            or candidate.requester_id != record.created_by
            or candidate.required_role != step.approver_role
            or candidate.user_id == record.created_by
            or (candidate.routing_source == "finance") != (step.approver_role == Role.FINANCE)
            or (
                candidate.routing_source == "department_manager"
                and not definition.allow_department_fallback
            )
            for candidate in candidates
        ):
            raise conflict("Candidate snapshot conflicts with the submitted plan.")
        if not candidates:
            raise conflict("Approval candidate snapshot is missing.")
        decision = session.scalar(
            select(ApprovalDecision).where(
                ApprovalDecision.organization_id == record.organization_id,
                ApprovalDecision.approval_id == step.id,
            )
        )
        if step.status in {"approved", "rejected"} and (
            decision is None or decision.outcome != step.status
        ):
            raise conflict("Approval decision evidence is incomplete.")
        if step.status == "pending" and decision is not None:
            raise conflict("Approval projection conflicts with decision evidence.")
        if decision is not None:
            event = session.scalar(
                select(RequestEvent).where(
                    RequestEvent.organization_id == record.organization_id,
                    RequestEvent.request_id == record.id,
                    RequestEvent.sequence == decision.event_sequence,
                )
            )
            if (
                event is None
                or decision.actor_id == record.created_by
                or decision.actor_id not in [candidate.user_id for candidate in candidates]
                or decision.required_role != step.approver_role
                or decision.requester_id != record.created_by
                or event.actor_id != decision.actor_id
                or event.reason != decision.reason
                or event.at != decision.at
                or event.action != ("approve" if decision.outcome == "approved" else "reject")
                or step.closed_event_sequence != event.sequence
                or step.decision_reason != decision.reason
                or step.decided_at != decision.at
            ):
                raise conflict("Prior decision conflicts with immutable history.")
    return steps


def submit(
    session: Session, actor: Principal, record: Request, action: Submit | Resubmit, now: datetime
) -> None:
    forbid_unless(record.created_by == actor.user_id)
    require_edge(record.type, record.status, Action(action.action), S.SUBMITTED)
    revision = None
    if isinstance(action, Resubmit):
        revision = latest_proposal(session, record, action.revision_id)
        data = parse_fields(record, revision.fields)
    else:
        data = action.data
    if data.type != record.type or record.workflow_version != 1:
        raise conflict("Submission does not match an actionable request type.")
    policy, plan = resolve_plan(session, record, data)
    if isinstance(action, Submit) and (
        session.scalar(
            select(Approval.id).where(
                Approval.organization_id == record.organization_id,
                Approval.request_id == record.id,
            )
        )
        is not None
    ):
        raise conflict("Draft already contains an approval plan requiring validation.")
    leave_overlap = False
    if isinstance(data, LeaveSubmission):
        # Flag overlapping submitted/approved leave for the same employee, never deny it.
        existing = session.execute(
            select(RequestFields)
            .join(
                Request,
                (
                    (Request.organization_id == RequestFields.organization_id)
                    & (Request.id == RequestFields.request_id)
                ),
            )
            .where(
                Request.organization_id == record.organization_id,
                Request.created_by == record.created_by,
                Request.type == T.LEAVE,
                Request.id != record.id,
                Request.status.in_([S.SUBMITTED, S.MANAGER_REVIEW, S.APPROVED, S.NEEDS_INFO]),
            )
        ).scalars()
        for other in existing:
            try:
                other_data = LeaveSubmission.model_validate({"type": "leave", **other.fields})
            except ValidationError:
                raise conflict(
                    "Existing leave dates require validation before overlap checking."
                ) from None
            if other_data.start_date <= data.end_date and data.start_date <= other_data.end_date:
                leave_overlap = True
    fields = session.get(RequestFields, (record.organization_id, record.id))
    if fields is None:
        fields = RequestFields(organization_id=record.organization_id, request_id=record.id)
        session.add(fields)
    fields.schema_version = 1
    fields.fields = data.model_dump(mode="json")
    record.leave_overlap = leave_overlap
    record.approval_policy_id = policy.id
    sequence = record.version + 1
    if record.submission_sequence is None:
        record.submission_sequence = sequence
    record.current_submission_sequence = sequence
    record.proposed_revision_id = None
    session.flush()  # Publish the new plan identity before inserting its guarded steps.
    persist_plan(session, record, plan)
    advance(session, actor, record, Action(action.action), S.SUBMITTED, action.reason, now)
    advance(
        session,
        actor,
        record,
        Action.ROUTE,
        S.MANAGER_REVIEW,
        f"Policy {policy.id} version {policy.version}: manager review",
        now,
    )
    if revision is None:
        revision = RequestRevision(
            id=uuid4(),
            organization_id=record.organization_id,
            request_id=record.id,
            event_sequence=sequence,
            actor_id=actor.user_id,
            at=now,
            kind="submitted",
            schema_version=1,
            fields=fields.fields,
            clarification="",
        )
        session.add(revision)
        session.flush()
    session.add(
        RequestSubmission(
            organization_id=record.organization_id,
            request_id=record.id,
            sequence=sequence,
            routing_sequence=sequence + 1,
            revision_id=revision.id,
            policy_id=policy.id,
            leave_overlap=record.leave_overlap,
        )
    )
    session.flush()


def close_pending(session: Session, record: Request) -> None:
    for step in session.scalars(
        select(Approval)
        .join(
            Request,
            (Request.organization_id == Approval.organization_id)
            & (Request.id == Approval.request_id),
        )
        .where(
            current_approval(),
            Approval.organization_id == record.organization_id,
            Approval.request_id == record.id,
            Approval.status == "pending",
        )
    ):
        step.status = "cancelled"
        step.closed_event_sequence = record.version


def actionable_step(
    session: Session,
    actor: Principal,
    record: Request,
    action: Approve | Reject | RequestChanges,
    now: datetime,
) -> tuple[list[Approval], Approval]:
    forbid_unless(actor.user_id != record.created_by)
    steps = validated_steps(session, record)
    step = next((item for item in steps if item.status == "pending"), None)
    if (
        step is None
        or step.id != action.approval_id
        or any(item.status != "approved" for item in steps if item.step < step.step)
    ):
        raise conflict("Only the current pending approval step can be decided.")
    review = S.MANAGER_REVIEW if step.approver_role == Role.MANAGER else S.FINANCE_REVIEW
    if record.status != review:
        raise conflict("Approval step does not match the current review state.")
    candidates = list(
        session.scalars(
            select(ApprovalCandidate).where(
                ApprovalCandidate.organization_id == record.organization_id,
                ApprovalCandidate.approval_id == step.id,
            )
        )
    )
    # Current eligibility uses only the historical snapshot; no substitute candidate is added.
    eligible = [
        candidate.user_id
        for candidate in candidates
        if candidate_eligible(session, record, candidate, lock=True)
    ]
    if not eligible:
        raise conflict("All snapshotted candidates are ineligible; approval is blocked.")
    forbid_unless(actor.user_id in eligible)
    return steps, step


def decide(
    session: Session, actor: Principal, record: Request, action: Approve | Reject, now: datetime
) -> UUID:
    steps, step = actionable_step(session, actor, record, action, now)
    outcome = "approved" if isinstance(action, Approve) else "rejected"
    target = (
        S.REJECTED
        if isinstance(action, Reject)
        else (S.FINANCE_REVIEW if any(item.step > step.step for item in steps) else S.APPROVED)
    )
    if target == S.APPROVED:
        record.approved_at = now
    advance(session, actor, record, Action(action.action), target, action.reason, now)
    decision = ApprovalDecision(
        id=uuid4(),
        organization_id=record.organization_id,
        approval_id=step.id,
        request_id=record.id,
        requester_id=record.created_by,
        actor_id=actor.user_id,
        required_role=step.approver_role,
        outcome=outcome,
        reason=action.reason,
        at=now,
        event_sequence=record.version,
    )
    session.add(decision)
    session.flush()
    step.status, step.decision_reason, step.decided_at = outcome, action.reason, now
    step.closed_event_sequence = record.version
    if isinstance(action, Reject):
        close_pending(session, record)
    session.flush()
    return decision.id


def current_sequence(record: Request) -> int:
    sequence = record.current_submission_sequence or record.submission_sequence
    if sequence is None:
        raise conflict("Submission evidence is missing.")
    return sequence


def parse_fields(record: Request, fields: dict[str, object]) -> ExpenseSubmission | LeaveSubmission:
    try:
        return (
            ExpenseSubmission.model_validate(fields)
            if record.type == T.EXPENSE
            else LeaveSubmission.model_validate(fields)
        )
    except ValidationError:
        raise conflict("Revision fields require validation.") from None


def correction(session: Session, record: Request) -> RequestChangeRequest:
    if record.status != S.NEEDS_INFO:
        raise conflict("Correction requires NEEDS_INFO.")
    result = session.scalar(
        select(RequestChangeRequest).where(
            RequestChangeRequest.organization_id == record.organization_id,
            RequestChangeRequest.request_id == record.id,
            RequestChangeRequest.submission_sequence == current_sequence(record),
        )
    )
    if result is None:
        raise conflict("Correction evidence is missing.")
    return result


def latest_proposal(session: Session, record: Request, revision_id: UUID) -> RequestRevision:
    change = correction(session, record)
    proposal = session.scalar(
        select(RequestRevision).where(
            RequestRevision.organization_id == record.organization_id,
            RequestRevision.request_id == record.id,
            RequestRevision.id == revision_id,
            RequestRevision.kind == "proposed",
            RequestRevision.change_sequence == change.event_sequence,
        )
    )
    if proposal is None or record.proposed_revision_id != revision_id:
        raise conflict("Resubmission requires the latest revision for this correction cycle.")
    return proposal


def capture_submission(session: Session, actor: Principal, record: Request, now: datetime) -> None:
    sequence = current_sequence(record)
    if session.get(RequestSubmission, (record.organization_id, record.id, sequence)) is not None:
        return
    # Capture only after validating immutable original submission and actual decision evidence.
    validated_steps(session, record)
    submitted = session.scalar(
        select(RequestEvent).where(
            RequestEvent.organization_id == record.organization_id,
            RequestEvent.request_id == record.id,
            RequestEvent.sequence == sequence,
        )
    )
    routed = session.scalar(
        select(RequestEvent).where(
            RequestEvent.organization_id == record.organization_id,
            RequestEvent.request_id == record.id,
            RequestEvent.sequence == sequence + 1,
        )
    )
    if (
        submitted is None
        or routed is None
        or submitted.action != "submit"
        or submitted.actor_id != record.created_by
        or submitted.from_state != S.DRAFT
        or submitted.to_state != S.SUBMITTED
        or routed.action != "route"
        or routed.actor_id != record.created_by
        or routed.from_state != S.SUBMITTED
        or routed.to_state != S.MANAGER_REVIEW
        or record.approval_policy_id is None
    ):
        raise conflict("Existing submission lacks trusted history; capture is blocked.")
    fields = session.get(RequestFields, (record.organization_id, record.id))
    if fields is None or fields.schema_version != 1:
        raise conflict("Existing submission fields require validation.")
    snapshot = RequestRevision(
        id=uuid4(),
        organization_id=record.organization_id,
        request_id=record.id,
        event_sequence=record.version + 1,
        actor_id=actor.user_id,
        at=now,
        kind="captured",
        schema_version=1,
        fields=fields.fields,
        clarification="",
    )
    session.add(snapshot)
    session.flush()
    session.add(
        RequestSubmission(
            organization_id=record.organization_id,
            request_id=record.id,
            sequence=sequence,
            routing_sequence=sequence + 1,
            revision_id=snapshot.id,
            policy_id=record.approval_policy_id,
            leave_overlap=record.leave_overlap,
        )
    )
    session.flush()


def revise(
    session: Session, actor: Principal, record: Request, action: Revise, now: datetime
) -> None:
    forbid_unless(record.created_by == actor.user_id)
    require_edge(record.type, record.status, Action.REVISE, S.NEEDS_INFO)
    change = correction(session, record)
    if action.data.type != record.type:
        raise conflict("Revision does not match the request type.")
    submission = session.get(
        RequestSubmission, (record.organization_id, record.id, current_sequence(record))
    )
    if submission is None:
        raise conflict("Submission snapshot is missing.")
    previous_id = record.proposed_revision_id or submission.revision_id
    previous = session.scalar(
        select(RequestRevision).where(
            RequestRevision.organization_id == record.organization_id,
            RequestRevision.request_id == record.id,
            RequestRevision.id == previous_id,
        )
    )
    if previous is None:
        raise conflict("Previous revision is missing.")
    fields = action.data.model_dump(mode="json")
    if previous.fields == fields and previous.clarification == action.clarification:
        raise conflict("Revision makes no change.")
    revision = RequestRevision(
        id=uuid4(),
        organization_id=record.organization_id,
        request_id=record.id,
        predecessor_id=previous.id,
        change_sequence=change.event_sequence,
        event_sequence=record.version + 1,
        actor_id=actor.user_id,
        at=now,
        kind="proposed",
        schema_version=1,
        fields=fields,
        clarification=action.clarification,
    )
    session.add(revision)
    record.proposed_revision_id = revision.id
    advance(session, actor, record, Action.REVISE, S.NEEDS_INFO, action.reason, now)


def apply(
    session: Session,
    actor: Principal,
    record: Request,
    action: Transition,
    roles: frozenset[Role],
    now: datetime,
) -> UUID | None:
    if isinstance(action, (Submit, Resubmit)):
        submit(session, actor, record, action, now)
    elif isinstance(action, RequestChanges):
        _, step = actionable_step(session, actor, record, action, now)
        capture_submission(session, actor, record, now)
        advance(session, actor, record, Action.REQUEST_CHANGES, S.NEEDS_INFO, action.reason, now)
        session.add(
            RequestChangeRequest(
                organization_id=record.organization_id,
                request_id=record.id,
                event_sequence=record.version,
                submission_sequence=current_sequence(record),
                approval_id=step.id,
                actor_id=actor.user_id,
                requester_id=record.created_by,
                required_role=step.approver_role,
            )
        )
        session.flush()
        close_pending(session, record)
    elif isinstance(action, Revise):
        revise(session, actor, record, action, now)
    elif isinstance(action, (Approve, Reject)):
        return decide(session, actor, record, action, now)
    elif isinstance(action, Process):
        forbid_unless(Role.FINANCE in roles and actor.user_id != record.created_by)
        require_edge(record.type, record.status, Action.PROCESS, S.COMPLETED)
        if (
            not all(step.status == "approved" for step in validated_steps(session, record))
            or record.approved_at is None
        ):
            raise conflict("Complete approval evidence is required before processing.")
        record.processed_by, record.processing_role = actor.user_id, Role.FINANCE
        record.completed_at, record.processing_reference = now, action.reference
        advance(session, actor, record, Action.PROCESS, S.COMPLETED, action.reason, now)
    elif isinstance(action, Cancel):
        if (
            record.approved_at is not None
            or record.completed_at is not None
            or record.processed_by is not None
        ):
            raise conflict("Final approval or completion prevents cancellation.")
        if record.type == T.SERVICE:
            if record.status == S.ASSIGNED:
                forbid_unless(
                    Role.ADMIN in roles
                    or department_manager(session, actor, record.department_id, lock=True)
                )
            else:
                forbid_unless(record.created_by == actor.user_id)
            advance(session, actor, record, Action.CANCEL, S.CANCELLED, action.reason, now)
        else:
            forbid_unless(record.created_by == actor.user_id)
            if record.status != S.DRAFT:
                validated_steps(session, record)
            elif record.workflow_version != 1:
                raise conflict("Legacy request requires explicit validation.")
            advance(session, actor, record, Action.CANCEL, S.WITHDRAWN, action.reason, now)
            close_pending(session, record)
    else:
        if record.type != T.SERVICE:
            raise conflict("Service action does not apply to this workflow.")
        if isinstance(action, (Triage, Assign)):
            forbid_unless(
                Role.ADMIN in roles
                or department_manager(session, actor, record.department_id, lock=True)
            )
            if isinstance(action, Triage):
                target = S.TRIAGED
            else:
                assignee = session.scalar(
                    select(User)
                    .where(
                        User.organization_id == record.organization_id,
                        User.id == action.assignee_id,
                        User.department_id == record.department_id,
                        User.status == "active",
                    )
                    .with_for_update(read=True)
                )
                if assignee is None or not active_roles(
                    session, Principal(actor.organization_id, action.assignee_id), lock=True
                ):
                    raise DomainError(
                        422, "Unprocessable Content", "Assignee is unavailable in this department."
                    )
                target = S.ASSIGNED
                record.assigned_to = action.assignee_id
        elif isinstance(action, (Start, Resolve)):
            forbid_unless(record.assigned_to == actor.user_id)
            target = S.IN_PROGRESS if isinstance(action, Start) else S.RESOLVED
            if isinstance(action, Resolve):
                record.resolution = action.resolution
        elif isinstance(action, Close):
            forbid_unless(record.created_by == actor.user_id or Role.ADMIN in roles)
            target = S.CLOSED
            record.completed_at = now
        else:
            raise conflict("Unknown workflow action.")
        advance(session, actor, record, Action(action.action), target, action.reason, now)
    return None


def transition(
    session: Session,
    actor: Principal,
    request_id: UUID,
    action: Transition,
    expected_version: int,
    key: UUID,
) -> TransitionRead:
    canonical = json.dumps(action.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    with session.begin():
        # Serialize keys across requests as well as retries on the same request.
        if session.get_bind().dialect.name == "postgresql":
            identity = f"{actor.organization_id}:{actor.user_id}:{key}"
            lock_id = int.from_bytes(hashlib.sha256(identity.encode()).digest()[:8], signed=True)
            session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})
        validate_principal(session, actor)
        record = scoped_request(session, actor, request_id, lock=True)
        roles = active_roles(session, actor, lock=True)
        forbid_unless(bool(roles))
        receipt = session.get(MutationReceipt, (actor.organization_id, actor.user_id, key))
        if receipt is not None:
            if (receipt.request_id, receipt.action, receipt.payload_hash) != (
                request_id,
                action.action,
                digest,
            ):
                raise conflict(
                    "Idempotency key was used for a different request, action, or payload."
                )
        else:
            if action.expected_version != expected_version or record.version != expected_version:
                raise DomainError(
                    409,
                    "Conflict",
                    f"Current request state is {record.status}, version {record.version}.",
                )
            decision_id = apply(session, actor, record, action, roles, datetime.now(UTC))
            receipt = MutationReceipt(
                organization_id=actor.organization_id,
                actor_id=actor.user_id,
                idempotency_key=key,
                request_id=request_id,
                action=action.action,
                payload_hash=digest,
                version=record.version,
                status=record.status,
                decision_id=decision_id,
            )
            session.add(receipt)
            session.flush()
        result = TransitionRead(
            outcome=TransitionOutcome.model_validate(receipt),
            request=request_detail(session, record),
        )
    return result
