"""Revision behavior exercised by the unit adapter and real PostgreSQL."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    ActiveApprovalPolicy,
    Approval,
    ApprovalPolicy,
    EmployeeManager,
    MutationReceipt,
    Request,
    RequestChangeRequest,
    RequestEvent,
    RequestRevision,
    RequestSubmission,
    RoleAssignment,
    User,
)
from app.domain.errors import DomainError
from app.domain.types import RequestType, Role
from app.schemas.core import RequestDetail
from app.services.requests import get_request, list_revisions
from app.services.visibility import actionable_approvals
from tests.workflow_support import World, add_actor, submission


def changes(
    world: World, kind: str = "expense", amount: str = "100.01", finance: bool = False
) -> RequestDetail:
    record = world.submit(kind, amount)
    if finance:
        record = world.act(
            record, world.manager, "approve", approval_id=str(record.approvals[0].id)
        ).request
    return world.act(
        record,
        world.finance if finance else world.manager,
        "request_changes",
        approval_id=str(record.approvals[-1 if finance else 0].id),
    ).request


def propose(
    world: World,
    record: RequestDetail,
    amount: str = "100.01",
    clarification: str = "Corrected context",
) -> RequestDetail:
    return world.act(
        record,
        world.owner,
        "revise",
        data=submission(record.type, amount),
        clarification=clarification,
    ).request


def resubmit(world: World, record: RequestDetail) -> RequestDetail:
    assert record.proposed_revision
    return world.act(
        record, world.owner, "resubmit", revision_id=str(record.proposed_revision.id)
    ).request


class RevisionCases:
    @pytest.mark.parametrize(
        "kind,finance", [("expense", False), ("expense", True), ("leave", False)]
    )
    def test_revision_full_reapproval_and_history(
        self, world: World, kind: str, finance: bool
    ) -> None:
        record = changes(world, kind, finance=finance)
        assert record.status == "NEEDS_INFO" and record.correction
        original = record.structured_fields
        old_ids = [step.id for step in record.approvals]
        old_decisions = [step.decision for step in record.approvals if step.decision]
        assert all(step.status != "pending" for step in record.approvals)
        for actor in (world.manager, world.finance):
            with Session(world.engine) as session:
                assert not session.scalars(
                    select(Approval)
                    .join(
                        Request,
                        Approval.request_id == Request.id,
                    )
                    .where(actionable_approvals(actor))
                ).all()
        proposed = propose(world, record)
        assert proposed.status == "NEEDS_INFO" and proposed.version == record.version + 1
        assert proposed.structured_fields == original and proposed.raw_text == record.raw_text
        assert (
            proposed.proposed_revision
            and proposed.proposed_revision.clarification == "Corrected context"
        )
        revised = resubmit(world, proposed)
        assert revised.version == proposed.version + 2 and revised.status == "MANAGER_REVIEW"
        assert all(
            step.status == "pending" and step.id not in old_ids for step in revised.approvals
        )
        assert revised.proposed_revision is None
        with pytest.raises(DomainError):
            world.act(revised, world.manager, "approve", approval_id=str(old_ids[0]))
        revised = world.act(
            revised, world.manager, "approve", approval_id=str(revised.approvals[0].id)
        ).request
        if kind == "expense":
            revised = world.act(
                revised, world.finance, "approve", approval_id=str(revised.approvals[1].id)
            ).request
            revised = world.act(
                revised, world.finance, "process", reference="Revision ledger"
            ).request
        with Session(world.engine) as session:
            history = list_revisions(session, world.owner, record.id, 100, 0)
            assert len(history.submissions) == 2
            assert [
                step.decision for step in history.submissions[0].approvals if step.decision
            ] == old_decisions
            assert history.items[0].fields == original

    @pytest.mark.parametrize("before", ["99.99", "100.00", "100.01"])
    @pytest.mark.parametrize("after", ["99.99", "100.00", "100.01"])
    def test_revision_threshold_all_boundaries(self, world: World, before: str, after: str) -> None:
        record = changes(world, amount=before)
        record = resubmit(world, propose(world, record, after))
        assert len(record.approvals) == (2 if after == "100.01" else 1)
        assert all(step.status == "pending" for step in record.approvals)
        assert record.structured_fields and record.structured_fields["amount"] == after

    def test_explanation_only_requires_new_manager_decision(self, world: World) -> None:
        record = changes(world, finance=True)
        record = resubmit(world, propose(world, record))
        assert record.status == "MANAGER_REVIEW"
        with pytest.raises(DomainError):
            world.act(record, world.finance, "approve", approval_id=str(record.approvals[1].id))
        with pytest.raises(DomainError):
            world.act(record, world.finance, "process", reference="Premature")

    @pytest.mark.parametrize("actor_name", ["owner", "admin", "finance", "colleague", "foreign"])
    def test_wrong_change_actor(self, world: World, actor_name: str) -> None:
        record = world.submit(amount="100.01")
        with pytest.raises(DomainError):
            world.act(
                record,
                getattr(world, actor_name),
                "request_changes",
                approval_id=str(record.approvals[0].id),
            )

    @pytest.mark.parametrize("action", ["revise", "resubmit"])
    @pytest.mark.parametrize("actor_name", ["manager", "finance", "admin", "colleague", "foreign"])
    def test_owner_only_revision(self, world: World, action: str, actor_name: str) -> None:
        record = propose(world, changes(world))
        assert record.proposed_revision
        extra = (
            {"data": submission(), "clarification": "Wrong actor"}
            if action == "revise"
            else {"revision_id": str(record.proposed_revision.id)}
        )
        with pytest.raises(DomainError):
            world.act(record, getattr(world, actor_name), action, **extra)

    @pytest.mark.parametrize("change", ["role", "user", "relationship"])
    def test_current_correction_eligibility(self, world: World, change: str) -> None:
        record = world.submit()
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
                record, world.manager, "request_changes", approval_id=str(record.approvals[0].id)
            )
        with Session(world.engine) as session:
            assert not session.scalar(select(func.count()).select_from(RequestChangeRequest))

    def test_latest_revision_current_cycle_and_noop(self, world: World) -> None:
        record = changes(world)
        with pytest.raises(DomainError):
            world.act(record, world.owner, "resubmit", revision_id=str(uuid4()))
        first = propose(world, record)
        second = propose(world, first, "99.99", "Second correction")
        assert first.proposed_revision and second.proposed_revision
        with pytest.raises(DomainError):
            world.act(second, world.owner, "resubmit", revision_id=str(first.proposed_revision.id))
        with pytest.raises(DomainError):
            propose(world, second, "99.99", "Second correction")
        submitted = resubmit(world, second)
        next_cycle = world.act(
            submitted, world.manager, "request_changes", approval_id=str(submitted.approvals[0].id)
        ).request
        with pytest.raises(DomainError):
            world.act(
                next_cycle, world.owner, "resubmit", revision_id=str(second.proposed_revision.id)
            )
        final = resubmit(world, propose(world, next_cycle, "99.99", "Third correction"))
        assert final.current_submission_sequence != submitted.current_submission_sequence

    @pytest.mark.parametrize("action", ["request_changes", "revise", "resubmit"])
    def test_exact_retry_and_stale_versions(self, world: World, action: str) -> None:
        record = world.submit() if action == "request_changes" else changes(world)
        if action == "resubmit":
            record = propose(world, record)
        actor = world.manager if action == "request_changes" else world.owner
        if action == "resubmit":
            assert record.proposed_revision
        revision_id = record.proposed_revision.id if record.proposed_revision else None
        extra = (
            {"approval_id": str(record.approvals[0].id)}
            if action == "request_changes"
            else (
                {"data": submission(), "clarification": "Retry context"}
                if action == "revise"
                else {"revision_id": str(revision_id)}
            )
        )
        key = uuid4()
        first = world.act(record, actor, action, key=key, **extra)
        assert world.act(record, actor, action, key=key, **extra) == first
        with pytest.raises(DomainError) as error:
            world.act(record, actor, action, **extra)
        assert error.value.status == 409
        with pytest.raises(DomainError):
            world.act(record, actor, action, key=key, reason="Different reason", **extra)
        with Session(world.engine) as session:
            counts = [
                session.scalar(select(func.count()).select_from(table))
                for table in (
                    RequestRevision,
                    RequestSubmission,
                    Request,
                    RequestChangeRequest,
                    RequestEvent,
                    MutationReceipt,
                )
            ]
        world.act(record, actor, action, key=key, **extra)
        with Session(world.engine) as session:
            assert counts == [
                session.scalar(select(func.count()).select_from(table))
                for table in (
                    RequestRevision,
                    RequestSubmission,
                    Request,
                    RequestChangeRequest,
                    RequestEvent,
                    MutationReceipt,
                )
            ]

    def test_withdrawal_and_no_terminal_revision(self, world: World) -> None:
        record = propose(world, changes(world, finance=True))
        record = world.act(record, world.owner, "cancel").request
        assert record.proposed_revision
        assert record.status == "WITHDRAWN" and record.approvals[0].decision
        with pytest.raises(DomainError):
            propose(world, record)
        with pytest.raises(DomainError):
            world.act(record, world.owner, "resubmit", revision_id=str(record.proposed_revision.id))

    def test_new_policy_manager_and_visibility(self, world: World) -> None:
        # An unacted finance nominee loses access after resubmission below the threshold.
        record = propose(world, changes(world), "99.99")
        new_manager = add_actor(world.engine, world.owner, world.department, (Role.MANAGER,))
        with Session(world.engine) as session, session.begin():
            relationship = session.get(
                EmployeeManager, (world.owner.organization_id, world.owner.user_id)
            )
            assert relationship
            relationship.manager_id = new_manager.user_id
            policy = ApprovalPolicy(
                id=uuid4(),
                organization_id=world.owner.organization_id,
                name="revised-expense",
                version=2,
                request_type=RequestType.EXPENSE,
                definition={
                    "schema_version": 1,
                    "allow_department_fallback": False,
                    "currency": "PKR",
                    "finance_threshold": "200.00",
                },
            )
            session.add(policy)
            session.flush()
            selected = session.get(
                ActiveApprovalPolicy, (world.owner.organization_id, RequestType.EXPENSE)
            )
            assert selected
            selected.policy_id = policy.id
        revised = resubmit(world, record)
        assert revised.approval_policy_id != record.approval_policy_id
        assert revised.approvals[0].candidates == [new_manager.user_id]
        for actor in (world.finance, world.admin, world.colleague, world.foreign):
            with Session(world.engine) as session, pytest.raises(DomainError):
                get_request(session, actor, revised.id)
            with Session(world.engine) as session, pytest.raises(DomainError):
                list_revisions(session, actor, revised.id, 20, 0)
        with Session(world.engine) as session:
            assert (
                get_request(session, world.manager, revised.id).id == revised.id
            )  # correction author retains role-scoped audit access
        with pytest.raises(DomainError):
            world.act(
                revised, world.manager, "request_changes", approval_id=str(revised.approvals[0].id)
            )

    @pytest.mark.parametrize("missing", ["policy", "manager", "finance", "invalid_policy"])
    def test_resubmission_failure_is_atomic(self, world: World, missing: str) -> None:
        record = propose(world, changes(world))
        with Session(world.engine) as session, session.begin():
            if missing == "policy":
                selected = session.get(
                    ActiveApprovalPolicy, (world.owner.organization_id, RequestType.EXPENSE)
                )
                assert selected
                session.delete(selected)
            elif missing == "invalid_policy":
                policy = ApprovalPolicy(
                    id=uuid4(),
                    organization_id=world.owner.organization_id,
                    name="invalid",
                    version=1,
                    request_type=RequestType.EXPENSE,
                    definition={},
                )
                session.add(policy)
                session.flush()
                selected = session.get(
                    ActiveApprovalPolicy, (world.owner.organization_id, RequestType.EXPENSE)
                )
                assert selected
                selected.policy_id = policy.id
            else:
                user = session.get(User, getattr(world, missing).user_id)
                assert user
                user.status = "inactive"
        with pytest.raises(DomainError) as error:
            resubmit(world, record)
        assert error.value.status == 409
        with Session(world.engine) as session:
            assert get_request(session, world.owner, record.id) == record
            assert session.scalar(select(func.count()).select_from(RequestSubmission)) == 1

    def test_leave_overlap_recomputed(self, world: World) -> None:
        other = changes(world, "leave")
        record = changes(world, "leave")
        assert record.leave_overlap
        data = {**submission("leave"), "start_date": "2027-01-01", "end_date": "2027-01-02"}
        record = world.act(
            record, world.owner, "revise", data=data, clarification="Changed dates"
        ).request
        record = resubmit(world, record)
        assert not record.leave_overlap
        assert other.status == "NEEDS_INFO"

    def test_service_and_multirole_self_changes_excluded(self, world: World) -> None:
        with Session(world.engine) as session, session.begin():
            session.add_all(
                RoleAssignment(
                    organization_id=world.owner.organization_id,
                    user_id=world.owner.user_id,
                    role=role,
                )
                for role in (Role.MANAGER, Role.FINANCE, Role.ADMIN)
            )
        record = world.submit()
        with pytest.raises(DomainError):
            world.act(
                record, world.owner, "request_changes", approval_id=str(record.approvals[0].id)
            )
        with pytest.raises(DomainError):
            world.act(
                world.create("service"), world.admin, "request_changes", approval_id=str(uuid4())
            )

    def test_delayed_change_retry_does_not_close_new_plan(self, world: World) -> None:
        record = world.submit(amount="100.01")
        key = uuid4()
        result = world.act(
            record,
            world.manager,
            "request_changes",
            key=key,
            approval_id=str(record.approvals[0].id),
        )
        current = resubmit(world, propose(world, result.request))
        retry = world.act(
            record,
            world.manager,
            "request_changes",
            key=key,
            approval_id=str(record.approvals[0].id),
        )
        assert retry.outcome == result.outcome and retry.request == current
        assert all(step.status == "pending" for step in retry.request.approvals)

    def test_superseded_unacted_manager_loses_access(self, world: World) -> None:
        second = add_actor(world.engine, world.owner, world.department, (Role.MANAGER,))
        from app.db.models import DepartmentManager

        with Session(world.engine) as session, session.begin():
            relationship = session.get(
                EmployeeManager, (world.owner.organization_id, world.owner.user_id)
            )
            assert relationship
            session.delete(relationship)
            session.add(
                DepartmentManager(
                    organization_id=world.owner.organization_id,
                    department_id=world.department,
                    manager_id=second.user_id,
                )
            )
            policy = ApprovalPolicy(
                id=uuid4(),
                organization_id=world.owner.organization_id,
                request_type=RequestType.LEAVE,
                name="fallback-revision",
                version=1,
                definition={"schema_version": 1, "allow_department_fallback": True},
            )
            session.add(policy)
            session.flush()
            selected = session.get(
                ActiveApprovalPolicy, (world.owner.organization_id, RequestType.LEAVE)
            )
            assert selected
            selected.policy_id = policy.id
        record = changes(world, "leave")
        assert second.user_id in record.approvals[0].candidates
        with Session(world.engine) as session:
            assert get_request(session, second, record.id).id == record.id
        with Session(world.engine) as session, session.begin():
            session.add(
                EmployeeManager(
                    organization_id=world.owner.organization_id,
                    employee_id=world.owner.user_id,
                    manager_id=world.manager.user_id,
                )
            )
        record = resubmit(world, propose(world, record))
        with Session(world.engine) as session, pytest.raises(DomainError):
            get_request(session, second, record.id)

    def test_correction_author_loses_audit_access_on_role_revocation(self, world: World) -> None:
        record = resubmit(world, propose(world, changes(world, finance=True), "99.99"))
        with Session(world.engine) as session:
            assert get_request(session, world.finance, record.id).id == record.id
        with Session(world.engine) as session, session.begin():
            role = session.get(
                RoleAssignment, (world.finance.organization_id, world.finance.user_id, Role.FINANCE)
            )
            assert role
            role.revoked_at = datetime.now(UTC)
        with Session(world.engine) as session, pytest.raises(DomainError):
            get_request(session, world.finance, record.id)

    @pytest.mark.parametrize("failed_action", ["request_changes", "resubmit", "route"])
    def test_revision_transition_event_failure_rolls_back(
        self, world: World, failed_action: str
    ) -> None:
        from sqlalchemy import event

        record = (
            world.submit() if failed_action == "request_changes" else propose(world, changes(world))
        )
        with Session(world.engine) as session:
            counts = [
                session.scalar(select(func.count()).select_from(table))
                for table in (
                    RequestRevision,
                    RequestSubmission,
                    RequestChangeRequest,
                    RequestEvent,
                    MutationReceipt,
                )
            ]

        def fail(session: Session, context: object, instances: object) -> None:
            if any(
                isinstance(item, RequestEvent) and item.action == failed_action
                for item in session.new
            ):
                raise RuntimeError("Injected transition event failure")

        event.listen(Session, "before_flush", fail)
        try:
            with pytest.raises(RuntimeError):
                if failed_action == "request_changes":
                    world.act(
                        record,
                        world.manager,
                        "request_changes",
                        approval_id=str(record.approvals[0].id),
                    )
                else:
                    resubmit(world, record)
        finally:
            event.remove(Session, "before_flush", fail)
        with Session(world.engine) as session:
            assert get_request(session, world.owner, record.id) == record
            assert counts == [
                session.scalar(select(func.count()).select_from(table))
                for table in (
                    RequestRevision,
                    RequestSubmission,
                    RequestChangeRequest,
                    RequestEvent,
                    MutationReceipt,
                )
            ]
