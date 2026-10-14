"""Shared acceptance tests for reversal, correction and service work cycles."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    ActiveServiceReopenPolicy,
    ApprovalDecision,
    CorrectionLink,
    Organization,
    ReversalDecision,
    ReversalRequest,
    RoleAssignment,
    ServiceReopenPolicy,
    ServiceResolution,
    User,
)
from app.domain.errors import DomainError
from app.domain.types import Role
from app.schemas.core import RequestDetail
from app.services.requests import get_request, list_lifecycle
from tests.workflow_support import World, submission


def approved(world: World, kind: str = "expense", amount: str = "100.00") -> RequestDetail:
    record = world.create(kind)
    data = submission(kind, amount)
    if kind == "leave":
        today = datetime.now(UTC).date()
        data.update(
            start_date=(today + timedelta(days=10)).isoformat(),
            end_date=(today + timedelta(days=12)).isoformat(),
        )
    record = world.act(record, world.owner, "submit", data=data).request
    record = world.act(
        record, world.manager, "approve", approval_id=str(record.approvals[0].id)
    ).request
    if record.status == "FINANCE_REVIEW":
        record = world.act(
            record, world.finance, "approve", approval_id=str(record.approvals[1].id)
        ).request
    return record


def held(
    world: World, kind: str = "expense", amount: str = "100.00", intent: str = "correct"
) -> RequestDetail:
    return world.act(
        approved(world, kind, amount), world.owner, "request_reversal", intent=intent
    ).request


def reverse(world: World, record: RequestDetail) -> RequestDetail:
    assert record.active_reversal
    actor = world.finance if len(record.approvals) == 2 else world.manager
    return world.act(
        record, actor, "approve_reversal", reversal_request_id=str(record.active_reversal.id)
    ).request


def resolved(world: World) -> RequestDetail:
    record = world.create("service")
    record = world.act(record, world.manager, "triage").request
    record = world.act(
        record, world.manager, "assign", assignee_id=str(world.colleague.user_id)
    ).request
    record = world.act(record, world.colleague, "start").request
    return world.act(record, world.colleague, "resolve", resolution="First resolution").request


def configure_reopen(world: World, seconds: int = 604800) -> UUID:
    policy_id = uuid4()
    with Session(world.engine) as session, session.begin():
        session.add(
            ServiceReopenPolicy(
                id=policy_id,
                organization_id=world.owner.organization_id,
                name="test-explicit-reopen",
                version=1,
                definition={"schema_version": 1, "window_seconds": seconds},
            )
        )
        session.flush()
        session.add(
            ActiveServiceReopenPolicy(
                organization_id=world.owner.organization_id, policy_id=policy_id
            )
        )
    return policy_id


class LifecycleCases:
    @pytest.mark.parametrize(
        "kind,amount", [("expense", "100.00"), ("expense", "100.01"), ("leave", "100.00")]
    )
    def test_reversal_correction_full_reapproval(
        self, world: World, kind: str, amount: str
    ) -> None:
        record = approved(world, kind, amount)
        original = record
        record = world.act(record, world.owner, "request_reversal", intent="correct").request
        assert record.status == "REVERSAL_REVIEW" and record.approved_at == original.approved_at
        with pytest.raises(DomainError):
            world.act(record, world.finance, "process", reference="Held")
        record = reverse(world, record)
        assert record.status == "REVERSED" and record.approvals == original.approvals
        assert (
            record.approved_at == original.approved_at
            and record.structured_fields == original.structured_fields
        )
        assert record.active_reversal
        key = uuid4()
        result = world.act(
            record,
            world.owner,
            "create_correction",
            key=key,
            reversal_request_id=str(record.active_reversal.id),
        )
        assert result.outcome.related_request_id
        retry = world.act(
            record,
            world.owner,
            "create_correction",
            key=key,
            reversal_request_id=str(record.active_reversal.id),
        )
        assert retry == result
        with Session(world.engine) as session:
            child = get_request(session, world.owner, result.outcome.related_request_id)
        assert child.status == "DRAFT" and not child.approvals and child.approved_at is None
        assert child.department_id == record.department_id and child.raw_text == record.raw_text
        assert child.correction_source_id == record.id
        assert child.current_submission_sequence is None
        data = submission(kind, "100.01") if kind == "expense" else original.structured_fields
        child = world.act(child, world.owner, "submit", data=data).request
        assert child.status == "MANAGER_REVIEW" and all(
            step.status == "pending" for step in child.approvals
        )
        assert all(step.id not in [old.id for old in record.approvals] for step in child.approvals)
        with Session(world.engine) as session:
            assert session.scalar(select(func.count()).select_from(CorrectionLink)) == 1
            assert get_request(session, world.owner, record.id).status == "REVERSED"
        with pytest.raises(DomainError):
            world.act(
                result.request,
                world.owner,
                "create_correction",
                reversal_request_id=str(record.active_reversal.id),
            )

    def test_denial_restores_original_authorization(self, world: World) -> None:
        original = approved(world)
        record = world.act(original, world.owner, "request_reversal", intent="withdraw").request
        assert record.active_reversal
        record = world.act(
            record,
            world.manager,
            "reject_reversal",
            reversal_request_id=str(record.active_reversal.id),
        ).request
        assert record.status == "APPROVED" and record.approved_at == original.approved_at
        assert record.approvals == original.approvals and record.reversal_decision
        assert record.reversal_decision.outcome == "denied"
        with Session(world.engine) as session:
            assert session.scalar(select(func.count()).select_from(ApprovalDecision)) == 1
        completed = world.act(
            record, world.finance, "process", reference="Existing authorization"
        ).request
        assert completed.status == "COMPLETED"
        with pytest.raises(DomainError):
            world.act(completed, world.owner, "request_reversal", intent="correct")

    @pytest.mark.parametrize("action", ["approve_reversal", "reject_reversal"])
    def test_requester_cannot_decide_even_with_multiple_roles(
        self, world: World, action: str
    ) -> None:
        with Session(world.engine) as session, session.begin():
            session.add_all(
                RoleAssignment(
                    organization_id=world.owner.organization_id,
                    user_id=world.owner.user_id,
                    role=role,
                )
                for role in (Role.MANAGER, Role.FINANCE, Role.ADMIN)
            )
        record = held(world)
        assert record.active_reversal
        with pytest.raises(DomainError):
            world.act(
                record, world.owner, action, reversal_request_id=str(record.active_reversal.id)
            )

    @pytest.mark.parametrize("action", ["approve_reversal", "reject_reversal"])
    def test_approver_initiator_cannot_decide_and_no_substitution(
        self, world: World, action: str
    ) -> None:
        record = approved(world)
        record = world.act(record, world.manager, "request_reversal", intent="withdraw").request
        assert record.active_reversal
        for actor in (
            world.manager,
            world.admin,
            world.finance,
            world.owner,
            world.colleague,
            world.foreign,
        ):
            with pytest.raises(DomainError):
                world.act(record, actor, action, reversal_request_id=str(record.active_reversal.id))
        with Session(world.engine) as session:
            assert get_request(session, world.owner, record.id).status == "REVERSAL_REVIEW"
            assert session.scalar(select(func.count()).select_from(ReversalDecision)) == 0

    def test_independent_finance_candidate_can_decide(self, world: World) -> None:
        with Session(world.engine) as session, session.begin():
            session.add(
                RoleAssignment(
                    organization_id=world.manager.organization_id,
                    user_id=world.manager.user_id,
                    role=Role.FINANCE,
                )
            )
        record = approved(world, amount="100.01")
        record = world.act(record, world.finance, "request_reversal", intent="withdraw").request
        assert record.active_reversal
        record = world.act(
            record,
            world.manager,
            "approve_reversal",
            reversal_request_id=str(record.active_reversal.id),
        ).request
        assert record.status == "REVERSED" and record.reversal_decision and record.active_reversal
        assert record.reversal_decision.actor_id != record.active_reversal.actor_id

    @pytest.mark.parametrize("actor_name", ["finance", "admin", "colleague", "foreign"])
    def test_no_processing_or_admin_only_reversal_authority(
        self, world: World, actor_name: str
    ) -> None:
        record = approved(world)
        with pytest.raises(DomainError):
            world.act(record, getattr(world, actor_name), "request_reversal", intent="withdraw")

    @pytest.mark.parametrize("change", ["role", "user", "relationship"])
    def test_decision_requires_current_eligibility(self, world: World, change: str) -> None:
        from app.db.models import EmployeeManager

        record = held(world)
        assert record.active_reversal
        with Session(world.engine) as session, session.begin():
            if change == "role":
                role = session.get(
                    RoleAssignment,
                    (world.manager.organization_id, world.manager.user_id, Role.MANAGER),
                )
                assert role
                role.revoked_at = datetime.now(UTC)
            elif change == "user":
                user = session.get(User, world.manager.user_id)
                assert user
                user.status = "inactive"
            else:
                relationship = session.get(
                    EmployeeManager, (world.owner.organization_id, world.owner.user_id)
                )
                assert relationship
                session.delete(relationship)
        with pytest.raises(DomainError):
            world.act(
                record,
                world.manager,
                "approve_reversal",
                reversal_request_id=str(record.active_reversal.id),
            )

    @pytest.mark.parametrize("offset", [-1, 0, 1])
    def test_leave_reversal_local_start_boundary(self, world: World, offset: int) -> None:
        with Session(world.engine) as session, session.begin():
            organization = session.get(Organization, world.owner.organization_id)
            assert organization
            organization.timezone = "Asia/Karachi"
        date = datetime.now(UTC).astimezone(ZoneInfo("Asia/Karachi")).date() + timedelta(
            days=offset
        )
        draft = world.create("leave")
        record = world.act(
            draft,
            world.owner,
            "submit",
            data={
                **submission("leave"),
                "start_date": date.isoformat(),
                "end_date": date.isoformat(),
            },
        ).request
        record = world.act(
            record, world.manager, "approve", approval_id=str(record.approvals[0].id)
        ).request
        if offset <= 0:
            with pytest.raises(DomainError) as error:
                world.act(record, world.owner, "request_reversal", intent="withdraw")
            assert error.value.status == 409
        else:
            assert (
                reverse(
                    world,
                    world.act(record, world.owner, "request_reversal", intent="withdraw").request,
                ).status
                == "REVERSED"
            )

    def test_started_leave_pending_can_be_denied_but_not_reversed(self, world: World) -> None:
        record = held(world, "leave")
        assert record.active_reversal
        # Probe the start-date cutoff with a deterministic service evaluation instant.
        from datetime import date

        from app.schemas.workflow import ApproveReversal
        from app.services import lifecycle

        assert record.structured_fields
        started = datetime.combine(
            date.fromisoformat(str(record.structured_fields["start_date"])),
            datetime.min.time(),
            UTC,
        )
        with Session(world.engine) as session, session.begin(), pytest.raises(DomainError):
            from app.db.models import Request

            current = session.get(Request, record.id)
            assert current
            lifecycle.decide_reversal(
                session,
                world.manager,
                current,
                ApproveReversal(
                    action="approve_reversal",
                    expected_version=record.version,
                    reason="Too late",
                    reversal_request_id=record.active_reversal.id,
                ),
                started,
            )
        record = world.act(
            record,
            world.manager,
            "reject_reversal",
            reversal_request_id=str(record.active_reversal.id),
        ).request
        assert record.status == "APPROVED"

    def test_withdrawal_reversal_cannot_create_correction(self, world: World) -> None:
        record = reverse(world, held(world, intent="withdraw"))
        assert record.active_reversal
        with pytest.raises(DomainError):
            world.act(
                record,
                world.owner,
                "create_correction",
                reversal_request_id=str(record.active_reversal.id),
            )

    @pytest.mark.parametrize("actor_name", ["owner", "manager", "admin"])
    def test_service_repeated_cycles_preserve_resolution(
        self, world: World, actor_name: str
    ) -> None:
        policy_id = configure_reopen(world)
        record = resolved(world)
        original = record
        assert record.current_resolution
        first_id = record.current_resolution.id
        record = world.act(
            record, getattr(world, actor_name), "reopen", resolution_id=str(first_id)
        ).request
        assert (
            record.status == "REOPENED"
            and record.resolution is None
            and record.current_resolution is None
        )
        assert record.assigned_to == original.assigned_to
        with pytest.raises(DomainError):
            world.act(record, world.owner, "close")
        record = world.act(record, world.colleague, "start").request
        record = world.act(
            record, world.colleague, "resolve", resolution="Second resolution"
        ).request
        assert record.current_resolution and record.current_resolution.id != first_id
        assert record.resolution == "Second resolution"
        record = world.act(
            record, world.owner, "reopen", resolution_id=str(record.current_resolution.id)
        ).request
        record = world.act(record, world.colleague, "start").request
        record = world.act(
            record, world.colleague, "resolve", resolution="Third resolution"
        ).request
        record = world.act(record, world.owner, "close").request
        assert record.status == "CLOSED" and record.resolution == "Third resolution"
        with pytest.raises(DomainError):
            world.act(record, world.admin, "reopen")
        with Session(world.engine) as session:
            history = list_lifecycle(session, world.owner, record.id, 100, 0)
            assert [item.body for item in history.resolutions] == [
                "First resolution",
                "Second resolution",
                "Third resolution",
            ]
            assert all(item.policy_id == policy_id for item in history.reopenings)
            assert session.scalar(select(func.count()).select_from(ServiceResolution)) == 3

    @pytest.mark.parametrize("actor_name", ["colleague", "finance", "foreign"])
    def test_service_reopen_wrong_actor(self, world: World, actor_name: str) -> None:
        configure_reopen(world)
        with pytest.raises(DomainError):
            world.act(resolved(world), getattr(world, actor_name), "reopen")

    @pytest.mark.parametrize("value", [None, 3599, 2592001, "604800", 3600.5])
    def test_service_policy_absent_invalid_no_default(self, world: World, value: object) -> None:
        record = resolved(world)
        if value is not None:
            with Session(world.engine) as session, session.begin():
                policy = ServiceReopenPolicy(
                    id=uuid4(),
                    organization_id=world.owner.organization_id,
                    name="invalid",
                    version=1,
                    definition={"schema_version": 1, "window_seconds": value},
                )
                session.add(policy)
                session.flush()
                session.add(
                    ActiveServiceReopenPolicy(
                        organization_id=world.owner.organization_id, policy_id=policy.id
                    )
                )
        with pytest.raises(DomainError) as error:
            world.act(record, world.owner, "reopen")
        assert error.value.status == 409
        with Session(world.engine) as session:
            assert get_request(session, world.owner, record.id) == record

    @pytest.mark.parametrize("change", ["inactive", "role", "department"])
    def test_service_retained_assignee_required(self, world: World, change: str) -> None:
        configure_reopen(world)
        record = resolved(world)
        with Session(world.engine) as session, session.begin():
            user = session.get(User, world.colleague.user_id)
            assert user
            if change == "inactive":
                user.status = "inactive"
            elif change == "department":
                user.department_id = None
            else:
                role = session.get(
                    RoleAssignment,
                    (world.colleague.organization_id, world.colleague.user_id, Role.EMPLOYEE),
                )
                assert role
                role.revoked_at = datetime.now(UTC)
        with pytest.raises(DomainError):
            world.act(record, world.owner, "reopen")

    @pytest.mark.parametrize(
        "action",
        ["request_reversal", "approve_reversal", "reject_reversal", "create_correction", "reopen"],
    )
    def test_exact_retries_and_stale_versions(self, world: World, action: str) -> None:
        actor = world.owner
        extra: dict[str, object]
        if action == "request_reversal":
            record = approved(world)
            extra = {"intent": "correct"}
        elif action == "reopen":
            configure_reopen(world)
            record = resolved(world)
            extra = {}
        else:
            record = held(world)
            assert record.active_reversal
            if action == "create_correction":
                record = reverse(world, record)
            else:
                actor = world.manager
            assert record.active_reversal
            extra = {"reversal_request_id": str(record.active_reversal.id)}
        key = uuid4()
        first = world.act(record, actor, action, key=key, **extra)
        assert world.act(record, actor, action, key=key, **extra) == first
        with pytest.raises(DomainError) as error:
            world.act(record, actor, action, key=None, **extra)
        assert error.value.status == 409
        with pytest.raises(DomainError):
            world.act(record, actor, action, key=key, reason="Different", **extra)

    def test_link_preserves_nonnull_due_and_independent_child_visibility(
        self, world: World
    ) -> None:
        from app.db.models import Request, RequestEvent

        now = datetime.now(UTC)
        due = now + timedelta(days=2)
        request_id = uuid4()
        with Session(world.engine) as session, session.begin():
            session.add(
                Request(
                    id=request_id,
                    organization_id=world.owner.organization_id,
                    created_by=world.owner.user_id,
                    department_id=world.department,
                    type="expense",
                    title="Due-bearing request",
                    raw_text="Original intake",
                    due_at=due,
                    status="DRAFT",
                    version=1,
                    workflow_version=1,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.flush()
            session.add(
                RequestEvent(
                    id=uuid4(),
                    organization_id=world.owner.organization_id,
                    request_id=request_id,
                    sequence=1,
                    actor_id=world.owner.user_id,
                    action="created",
                    from_state=None,
                    to_state="DRAFT",
                    reason="Fixture creation",
                    at=now,
                )
            )
        with Session(world.engine) as session:
            record = get_request(session, world.owner, request_id)
        record = world.act(record, world.owner, "submit", data=submission()).request
        record = world.act(
            record, world.manager, "approve", approval_id=str(record.approvals[0].id)
        ).request
        record = reverse(
            world, world.act(record, world.owner, "request_reversal", intent="correct").request
        )
        assert record.active_reversal
        result = world.act(
            record,
            world.owner,
            "create_correction",
            reversal_request_id=str(record.active_reversal.id),
        )
        child_id = result.outcome.related_request_id
        assert child_id
        with Session(world.engine) as session:
            child = session.get(Request, child_id)
            parent = session.get(Request, request_id)
            assert child and parent
            assert child.due_at == parent.due_at
            assert get_request(session, world.manager, record.id).replacement_request_id is None
        with Session(world.engine) as session, pytest.raises(DomainError):
            get_request(session, world.manager, child_id)
        with Session(world.engine) as session, pytest.raises(DomainError):
            list_lifecycle(session, world.admin, request_id, 20, 0)

    def test_delayed_retries_do_not_change_new_work_or_review(self, world: World) -> None:
        record = approved(world)
        key = uuid4()
        first = world.act(record, world.owner, "request_reversal", key=key, intent="withdraw")
        assert first.request.active_reversal
        denied = world.act(
            first.request,
            world.manager,
            "reject_reversal",
            reversal_request_id=str(first.request.active_reversal.id),
        ).request
        later = world.act(denied, world.owner, "request_reversal", intent="correct").request
        retry = world.act(record, world.owner, "request_reversal", key=key, intent="withdraw")
        assert retry.outcome == first.outcome and retry.request == later
        configure_reopen(world)
        service = resolved(world)
        reopen_key = uuid4()
        first_reopen = world.act(service, world.owner, "reopen", key=reopen_key)
        current = world.act(first_reopen.request, world.colleague, "start").request
        current = world.act(
            current, world.colleague, "resolve", resolution="New resolution"
        ).request
        current = world.act(current, world.owner, "close").request
        retry = world.act(service, world.owner, "reopen", key=reopen_key)
        assert retry.outcome == first_reopen.outcome and retry.request == current

    def test_no_history_substitution_and_no_requester_edits(self, world: World) -> None:
        record = held(world)
        assert record.active_reversal
        with pytest.raises(DomainError):
            world.act(record, world.manager, "approve_reversal", reversal_request_id=str(uuid4()))
        with pytest.raises(DomainError):
            world.act(
                record,
                world.owner,
                "revise",
                data=submission(),
                clarification="Forbidden approved edit",
            )
        with pytest.raises(DomainError):
            world.act(record, world.owner, "cancel")
        configure_reopen(world)
        service = resolved(world)
        assert service.current_resolution
        old_id = service.current_resolution.id
        service = world.act(service, world.owner, "reopen").request
        service = world.act(service, world.colleague, "start").request
        service = world.act(
            service, world.colleague, "resolve", resolution="Next resolution"
        ).request
        with pytest.raises(DomainError):
            world.act(service, world.owner, "reopen", resolution_id=str(old_id))

    @pytest.mark.parametrize(
        "action",
        [
            "request_reversal",
            "approve_reversal",
            "reject_reversal",
            "create_correction",
            "reopen",
            "resolve",
        ],
    )
    def test_lifecycle_event_failure_rolls_back(self, world: World, action: str) -> None:
        from sqlalchemy import event

        from app.db.models import RequestEvent, ServiceReopening

        actor = world.owner
        extra: dict[str, object]
        if action == "request_reversal":
            record = approved(world)
            extra = {"intent": "correct"}
        elif action in ("reopen", "resolve"):
            configure_reopen(world)
            record = resolved(world)
            if action == "resolve":
                record = world.act(record, world.owner, "reopen").request
                record = world.act(record, world.colleague, "start").request
                actor = world.colleague
                extra = {"resolution": "Rollback resolution"}
            else:
                extra = {}
        else:
            record = held(world)
            if action == "create_correction":
                record = reverse(world, record)
            else:
                actor = world.manager
            assert record.active_reversal
            extra = {"reversal_request_id": str(record.active_reversal.id)}

        def fail(session: Session, context: object, instances: object) -> None:
            if any(
                isinstance(item, RequestEvent) and item.action == action for item in session.new
            ):
                raise RuntimeError("Injected lifecycle event failure")

        with Session(world.engine) as session:
            counts = [
                session.scalar(select(func.count()).select_from(table))
                for table in (
                    ReversalRequest,
                    ReversalDecision,
                    ReversalRequest,
                    CorrectionLink,
                    ServiceResolution,
                    ServiceReopening,
                )
            ]
        event.listen(Session, "before_flush", fail)
        try:
            with pytest.raises(RuntimeError):
                world.act(record, actor, action, key=None, **extra)
        finally:
            event.remove(Session, "before_flush", fail)
        with Session(world.engine) as session:
            assert get_request(session, world.owner, record.id) == record
            assert counts == [
                session.scalar(select(func.count()).select_from(table))
                for table in (
                    ReversalRequest,
                    ReversalDecision,
                    ReversalRequest,
                    CorrectionLink,
                    ServiceResolution,
                    ServiceReopening,
                )
            ]

    @pytest.mark.parametrize("microseconds", [-1, 0, 1])
    def test_reopen_inclusive_policy_boundary(self, world: World, microseconds: int) -> None:
        from app.db.models import Request
        from app.schemas.workflow import Reopen
        from app.services import lifecycle

        configure_reopen(world, 3600)
        record = resolved(world)
        assert record.current_resolution
        instant = record.current_resolution.at + timedelta(seconds=3600, microseconds=microseconds)
        with Session(world.engine) as session:
            if microseconds > 0:
                with session.begin(), pytest.raises(DomainError) as error:
                    current = session.get(Request, record.id)
                    assert current
                    lifecycle.reopen(
                        session,
                        world.owner,
                        current,
                        Reopen(
                            action="reopen",
                            expected_version=record.version,
                            reason="Boundary probe",
                        ),
                        frozenset({Role.EMPLOYEE}),
                        instant,
                    )
                assert error.value.status == 409
            else:
                with session.begin():
                    current = session.get(Request, record.id)
                    assert current
                    lifecycle.reopen(
                        session,
                        world.owner,
                        current,
                        Reopen(
                            action="reopen",
                            expected_version=record.version,
                            reason="Boundary probe",
                        ),
                        frozenset({Role.EMPLOYEE}),
                        instant,
                    )
                assert get_request(session, world.owner, record.id).status == "REOPENED"
