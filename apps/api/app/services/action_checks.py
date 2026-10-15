"""Read-only preconditions shared by capability reads and locked new mutations.

This module never adds, flushes, captures or advances workflow evidence. Payload-free
checks authorize opening a typed form; payload validation still occurs on mutation.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Approval, Request, RequestEvent
from app.domain.identity import Principal
from app.domain.types import RequestStatus as S
from app.domain.types import RequestType as T
from app.domain.types import Role
from app.domain.workflow import EDGES, Action
from app.schemas.capabilities import ActionCapability
from app.schemas.workflow import Resubmit, Submit, Transition
from app.services.eligibility import (
    active_roles,
    assignee_query,
    department_manager,
    require_assignee,
)


def check_action(
    session: Session,
    actor: Principal,
    record: Request,
    action: Action,
    now: datetime,
    *,
    payload: Transition | None = None,
    lock: bool = False,
) -> ActionCapability:
    from app.services import lifecycle
    from app.services.policies import resolve_plan
    from app.services.transition_service import (
        actionable_step,
        conflict,
        correction,
        forbid_unless,
        latest_proposal,
        parse_fields,
        revision_base,
        submission_overlap,
        validated_steps,
    )

    roles = active_roles(session, actor, lock=lock)
    forbid_unless(bool(roles))
    targets = EDGES.get((record.type, record.status, action))
    if not targets or action == Action.ROUTE:
        raise conflict("Action is not allowed in the current state.")
    result = ActionCapability(action=action)
    if action in (Action.APPROVE, Action.REJECT, Action.REQUEST_CHANGES):
        _, step = actionable_step(session, actor, record, None, now, lock=lock)
        result.approval_id = step.id
    elif action in (Action.SUBMIT, Action.RESUBMIT):
        forbid_unless(record.created_by == actor.user_id)
        if record.workflow_version != 1:
            raise conflict("Legacy request requires explicit validation.")
        data = None
        if action == Action.RESUBMIT:
            if record.proposed_revision_id is None:
                raise conflict("A proposed revision is required.")
            proposal = latest_proposal(session, record, record.proposed_revision_id)
            data = parse_fields(record, proposal.fields)
            result.revision_id = proposal.id
        else:
            if (
                session.scalar(
                    select(Approval.id).where(
                        Approval.organization_id == record.organization_id,
                        Approval.request_id == record.id,
                    )
                )
                is not None
            ):
                raise conflict("Draft already contains a plan requiring validation.")
            if isinstance(payload, Submit):
                data = payload.data
        if data is not None and data.type != record.type:
            raise conflict("Submission type does not match the request.")
        if isinstance(payload, Resubmit):
            latest_proposal(session, record, payload.revision_id)
        resolve_plan(session, record, data, lock=lock)
        if data is not None:
            submission_overlap(session, record, data)
    elif action == Action.REVISE:
        revision_base(session, actor, record)
    elif action == Action.PROCESS:
        forbid_unless(Role.FINANCE in roles and actor.user_id != record.created_by)
        if (
            not all(step.status == "approved" for step in validated_steps(session, record))
            or record.approved_at is None
        ):
            raise conflict("Complete approval evidence is required before processing.")
    elif action == Action.CANCEL:
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
                    or department_manager(session, actor, record.department_id, lock=lock)
                )
            else:
                forbid_unless(record.created_by == actor.user_id)
        else:
            forbid_unless(record.created_by == actor.user_id)
            if record.status != S.DRAFT:
                validated_steps(session, record)
                if record.status == S.NEEDS_INFO:
                    correction(session, record)
            elif record.workflow_version != 1:
                raise conflict("Legacy request requires explicit validation.")
    elif action == Action.REQUEST_REVERSAL:
        lifecycle.check_request_reversal(session, actor, record, now, lock=lock)
    elif action in (Action.APPROVE_REVERSAL, Action.REJECT_REVERSAL):
        if record.active_reversal_id is None:
            raise conflict("Active reversal evidence is missing.")
        lifecycle.check_decide_reversal(
            session, actor, record, action, record.active_reversal_id, now, lock=lock
        )
        result.reversal_request_id = record.active_reversal_id
    elif action == Action.CREATE_CORRECTION:
        if record.active_reversal_id is None:
            raise conflict("Active reversal evidence is missing.")
        lifecycle.check_create_correction(session, actor, record, record.active_reversal_id)
        result.reversal_request_id = record.active_reversal_id
    elif action == Action.REOPEN:
        resolution, _, _ = lifecycle.check_reopen(session, actor, record, roles, now, lock=lock)
        result.resolution_id = resolution.id
    elif action in (Action.TRIAGE, Action.ASSIGN):
        forbid_unless(
            Role.ADMIN in roles
            or department_manager(session, actor, record.department_id, lock=lock)
        )
        if action == Action.ASSIGN:
            if payload is not None:
                from app.schemas.workflow import Assign

                assert isinstance(payload, Assign)
                require_assignee(session, record, payload.assignee_id, lock=lock)
            elif session.scalar(assignee_query(record).limit(1)) is None:
                raise conflict("No eligible service assignee is available.")
    elif action in (Action.START, Action.RESOLVE):
        forbid_unless(record.assigned_to == actor.user_id)
        if record.status == S.REOPENED:
            lifecycle.valid_assignee(session, record, lock=lock)
        if (
            action == Action.RESOLVE
            and record.workflow_version == 1
            and record.service_cycle_sequence is None
        ):
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
    elif action == Action.CLOSE:
        forbid_unless(record.created_by == actor.user_id or Role.ADMIN in roles)
        if record.workflow_version == 1 and record.service_cycle_sequence is not None:
            lifecycle.resolution_evidence(session, record)
    return result
