"""Behavioral acceptance cases run against both SQLite and live PostgreSQL."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.db.models import (
    ActiveApprovalPolicy,
    Approval,
    ApprovalCandidate,
    ApprovalDecision,
    ApprovalPolicy,
    DepartmentManager,
    EmployeeManager,
    MutationReceipt,
    RequestEvent,
    RoleAssignment,
    User,
)
from app.domain.errors import DomainError
from app.domain.types import RequestType, Role
from app.schemas.workflow import transition_adapter
from app.services.requests import get_request, list_requests
from app.services.visibility import WorkScope
from tests.workflow_support import World, add_actor, submission


class WorkflowCases:
    def test_service_journey(self, world: World) -> None:
        record = world.create("service")
        record = world.act(record, world.manager, "triage").request
        record = world.act(
            record, world.admin, "assign", assignee_id=str(world.colleague.user_id)
        ).request
        record = world.act(record, world.colleague, "start").request
        record = world.act(
            record, world.colleague, "resolve", resolution="Synthetic repair"
        ).request
        record = world.act(record, world.owner, "close").request
        assert record.status == "CLOSED" and record.version == 6
        assert record.resolution == "Synthetic repair" and record.completed_at is not None
        assert [e.action for e in record.status_history] == [
            "created",
            "triage",
            "assign",
            "start",
            "resolve",
            "close",
        ]
        with pytest.raises(DomainError) as error:
            world.act(record, world.admin, "triage")
        assert error.value.status == 409

    @pytest.mark.parametrize(
        "amount,finance", [("99.99", False), ("100.00", False), ("100.01", True)]
    )
    def test_expense_threshold_and_processing(
        self, world: World, amount: str, finance: bool
    ) -> None:
        record = world.submit(amount=amount)
        assert record.version == 3 and record.status == "MANAGER_REVIEW"
        assert [e.to_state for e in record.status_history] == [
            "DRAFT",
            "SUBMITTED",
            "MANAGER_REVIEW",
        ]
        assert len(record.approvals) == (2 if finance else 1)
        record = world.act(
            record, world.manager, "approve", approval_id=str(record.approvals[0].id)
        ).request
        if finance:
            assert record.status == "FINANCE_REVIEW" and record.approved_at is None
            record = world.act(
                record, world.finance, "approve", approval_id=str(record.approvals[1].id)
            ).request
        assert (
            record.status == "APPROVED"
            and record.processed_by is None
            and record.completed_at is None
        )
        record = world.act(
            record, world.finance, "process", reference="Synthetic ledger reference"
        ).request
        assert record.status == "COMPLETED" and record.processed_by == world.finance.user_id
        assert record.processing_reference == "Synthetic ledger reference"
        assert all(step.decision is not None for step in record.approvals)
        assert record.completed_at is not None

    def test_leave_terminal_and_overlap(self, world: World) -> None:
        record = world.submit("leave")
        assert not record.leave_overlap
        second = world.submit("leave")
        assert second.leave_overlap
        record = world.act(
            record, world.manager, "approve", approval_id=str(record.approvals[0].id)
        ).request
        assert record.status == "APPROVED" and record.completed_at is None
        for action, actor, extra in (
            ("cancel", world.owner, {}),
            ("process", world.finance, {"reference": "Synthetic"}),
        ):
            with pytest.raises(DomainError) as error:
                world.act(record, actor, action, key=None, **extra)
            assert error.value.status in {404, 409}

    @pytest.mark.parametrize("kind", ["expense", "leave"])
    def test_rejection_closes_future_steps(self, world: World, kind: str) -> None:
        record = world.submit(kind, "100.01")
        record = world.act(
            record, world.manager, "reject", approval_id=str(record.approvals[0].id)
        ).request
        assert record.status == "REJECTED"
        assert record.approvals[0].decision is not None
        if kind == "expense":
            assert (
                record.approvals[1].status == "cancelled" and record.approvals[1].decision is None
            )
        with pytest.raises(DomainError):
            world.act(record, world.owner, "cancel")

    def test_finance_reject_and_owner_withdrawal(self, world: World) -> None:
        record = world.submit(amount="100.01")
        record = world.act(
            record, world.manager, "approve", approval_id=str(record.approvals[0].id)
        ).request
        withdrawn = world.act(record, world.owner, "cancel").request
        assert withdrawn.status == "WITHDRAWN"
        assert (
            withdrawn.approvals[0].status == "approved"
            and withdrawn.approvals[0].decision is not None
        )
        assert (
            withdrawn.approvals[1].status == "cancelled" and withdrawn.approvals[1].decision is None
        )
        another = world.submit(amount="100.01")
        another = world.act(
            another, world.manager, "approve", approval_id=str(another.approvals[0].id)
        ).request
        rejected = world.act(
            another, world.finance, "reject", approval_id=str(another.approvals[1].id)
        ).request
        assert (
            rejected.status == "REJECTED"
            and len([a for a in rejected.approvals if a.decision]) == 2
        )

    @pytest.mark.parametrize("kind", ["expense", "leave"])
    @pytest.mark.parametrize("submitted", [False, True])
    def test_withdraw_before_approval(self, world: World, kind: str, submitted: bool) -> None:
        record = world.submit(kind) if submitted else world.create(kind)
        record = world.act(record, world.owner, "cancel").request
        assert record.status == "WITHDRAWN"
        assert all(step.status == "cancelled" for step in record.approvals)
        assert not any(step.decision for step in record.approvals)

    @pytest.mark.parametrize(
        "stage", ["SUBMITTED", "TRIAGED", "ASSIGNED", "IN_PROGRESS", "RESOLVED", "CLOSED"]
    )
    def test_conservative_service_cancel(self, world: World, stage: str) -> None:
        record = world.create("service")
        if stage != "SUBMITTED":
            record = world.act(record, world.manager, "triage").request
        if stage in {"ASSIGNED", "IN_PROGRESS", "RESOLVED", "CLOSED"}:
            record = world.act(
                record, world.manager, "assign", assignee_id=str(world.colleague.user_id)
            ).request
        if stage in {"IN_PROGRESS", "RESOLVED", "CLOSED"}:
            record = world.act(record, world.colleague, "start").request
        if stage in {"RESOLVED", "CLOSED"}:
            record = world.act(
                record, world.colleague, "resolve", resolution="Synthetic repair"
            ).request
        if stage == "CLOSED":
            record = world.act(record, world.owner, "close").request
        actor = world.manager if stage == "ASSIGNED" else world.owner
        if stage in {"IN_PROGRESS", "RESOLVED", "CLOSED"}:
            with pytest.raises(DomainError):
                world.act(record, actor, "cancel")
        else:
            assert world.act(record, actor, "cancel").request.status == "CANCELLED"

    def test_self_approval_admin_and_processing_bypass(self, world: World) -> None:
        with Session(world.engine) as session, session.begin():
            session.add_all(
                RoleAssignment(
                    organization_id=world.owner.organization_id,
                    user_id=world.owner.user_id,
                    role=role,
                )
                for role in (Role.MANAGER, Role.FINANCE, Role.ADMIN)
            )
        record = world.submit(amount="100.01")
        for actor in (world.owner, world.admin, world.colleague, world.finance, world.foreign):
            with pytest.raises(DomainError) as error:
                world.act(record, actor, "approve", approval_id=str(record.approvals[0].id))
            assert error.value.status in {403, 404}
        record = world.act(
            record, world.manager, "approve", approval_id=str(record.approvals[0].id)
        ).request
        record = world.act(
            record, world.finance, "approve", approval_id=str(record.approvals[1].id)
        ).request
        for actor in (world.owner, world.manager, world.admin, world.colleague, world.foreign):
            with pytest.raises(DomainError):
                world.act(record, actor, "process", reference="Synthetic")
        with pytest.raises(DomainError):
            world.act(record, world.owner, "cancel")

    def test_same_nonrequester_can_hold_all_required_roles(self, world: World) -> None:
        with Session(world.engine) as session, session.begin():
            session.add(
                RoleAssignment(
                    organization_id=world.manager.organization_id,
                    user_id=world.manager.user_id,
                    role=Role.FINANCE,
                )
            )
        record = world.submit(amount="100.01")
        record = world.act(
            record, world.manager, "approve", approval_id=str(record.approvals[0].id)
        ).request
        record = world.act(
            record, world.manager, "approve", approval_id=str(record.approvals[1].id)
        ).request
        record = world.act(record, world.manager, "process", reference="Synthetic").request
        assert record.processed_by == world.manager.user_id
        assert [a.decision.actor_id for a in record.approvals if a.decision] == [
            world.manager.user_id
        ] * 2
        assert [e.action for e in record.status_history[-3:]] == ["approve", "approve", "process"]

    @pytest.mark.parametrize("change", ["revoked", "inactive", "relationship"])
    def test_current_eligibility_does_not_replace_snapshot(self, world: World, change: str) -> None:
        record = world.submit()
        with Session(world.engine) as session, session.begin():
            if change == "revoked":
                role = session.get(
                    RoleAssignment,
                    (world.manager.organization_id, world.manager.user_id, Role.MANAGER),
                )
                assert role
                role.revoked_at = datetime.now(UTC)
            elif change == "inactive":
                user = session.get(User, world.manager.user_id)
                assert user
                user.status = "inactive"
            else:
                relationship = session.get(
                    EmployeeManager, (world.owner.organization_id, world.owner.user_id)
                )
                assert relationship
                session.delete(relationship)
        # Owner still sees the plan; a new department manager is never substituted.
        with pytest.raises(DomainError):
            world.act(record, world.manager, "approve", approval_id=str(record.approvals[0].id))
        with Session(world.engine) as session:
            current = get_request(session, world.owner, record.id)
        assert current.version == record.version and current.approvals[0].candidates == [
            world.manager.user_id
        ]

    @pytest.mark.parametrize("fallback", [False, True])
    def test_precedence_fallback_and_one_of(self, world: World, fallback: bool) -> None:
        second = add_actor(world.engine, world.owner, world.department, (Role.MANAGER,))
        with Session(world.engine) as session, session.begin():
            session.add(
                DepartmentManager(
                    organization_id=world.owner.organization_id,
                    department_id=world.department,
                    manager_id=second.user_id,
                )
            )
            selected = session.get(
                ActiveApprovalPolicy, (world.owner.organization_id, RequestType.LEAVE)
            )
            assert selected
            policy = ApprovalPolicy(
                id=uuid4(),
                organization_id=world.owner.organization_id,
                request_type=RequestType.LEAVE,
                name="test-leave",
                version=2,
                definition={"schema_version": 1, "allow_department_fallback": fallback},
            )
            session.add(policy)
            session.flush()
            selected.policy_id = policy.id
        explicit = world.submit("leave")
        assert explicit.approvals[0].candidates == [world.manager.user_id]
        with Session(world.engine) as session, session.begin():
            relationship = session.get(
                EmployeeManager, (world.owner.organization_id, world.owner.user_id)
            )
            assert relationship
            session.delete(relationship)
        draft = world.create("leave")
        if not fallback:
            with pytest.raises(DomainError) as error:
                world.act(draft, world.owner, "submit", data=submission("leave"))
            assert error.value.status == 409
        else:
            record = world.act(draft, world.owner, "submit", data=submission("leave")).request
            assert set(record.approvals[0].candidates) == {world.manager.user_id, second.user_id}
            record = world.act(
                record, second, "approve", approval_id=str(record.approvals[0].id)
            ).request
            assert record.status == "APPROVED" and len(record.approvals) == 1

    def test_missing_policy_or_finance_fails_atomically(self, world: World) -> None:
        with Session(world.engine) as session, session.begin():
            user = session.get(User, world.finance.user_id)
            assert user
            user.status = "inactive"
        draft = world.create()
        with pytest.raises(DomainError) as error:
            world.act(draft, world.owner, "submit", data=submission(amount="100.01"))
        assert error.value.status == 409
        with Session(world.engine) as session:
            current = get_request(session, world.owner, draft.id)
            assert (
                current.version == 1 and not current.approvals and current.structured_fields is None
            )
        with Session(world.engine) as session, session.begin():
            selected = session.get(
                ActiveApprovalPolicy, (world.owner.organization_id, RequestType.EXPENSE)
            )
            assert selected
            session.delete(selected)
        with pytest.raises(DomainError) as error:
            world.act(draft, world.owner, "submit", data=submission())
        assert error.value.status == 409

    def test_retries_bind_actor_request_action_and_payload(self, world: World) -> None:
        draft = world.create()
        key = uuid4()
        first = world.act(draft, world.owner, "submit", key=key, data=submission())
        retry = world.act(draft, world.owner, "submit", key=key, data=submission(amount="100"))
        assert first == retry  # Decimal representations canonicalize identically.
        with pytest.raises(DomainError) as error:
            world.act(draft, world.owner, "submit", key=key, data=submission(amount="99.99"))
        assert error.value.status == 409
        other = world.create()
        with pytest.raises(DomainError):
            world.act(other, world.owner, "submit", key=key, data=submission())
        record = first.request
        decision_key = uuid4()
        decision = world.act(
            record,
            world.manager,
            "approve",
            key=decision_key,
            approval_id=str(record.approvals[0].id),
        )
        assert (
            world.act(
                record,
                world.manager,
                "approve",
                key=decision_key,
                approval_id=str(record.approvals[0].id),
            )
            == decision
        )
        world.act(decision.request, world.finance, "process", reference="Synthetic")
        retried = world.act(
            record,
            world.manager,
            "approve",
            key=decision_key,
            approval_id=str(record.approvals[0].id),
        )
        assert retried.outcome == decision.outcome and retried.request.status == "COMPLETED"
        with Session(world.engine) as session:
            assert session.scalar(select(func.count()).select_from(ApprovalDecision)) == 1
            assert session.scalar(select(func.count()).select_from(MutationReceipt)) == 3
        with pytest.raises(DomainError):
            world.act(record, world.manager, "approve", approval_id=str(record.approvals[0].id))

    def test_participant_visibility_and_work_scopes(self, world: World) -> None:
        record = world.submit(amount="100.01")
        for actor in (world.admin, world.colleague, world.foreign):
            with Session(world.engine) as session, pytest.raises(DomainError) as error:
                get_request(session, actor, record.id)
            assert error.value.status == 404
            with Session(world.engine) as session:
                assert not list_requests(session, actor, 20, 0, WorkScope.PARTICIPANT).items
        for actor in (world.manager, world.finance):
            with Session(world.engine) as session:
                assert get_request(session, actor, record.id).id == record.id
                assert [
                    r.id for r in list_requests(session, actor, 1, 0, WorkScope.PARTICIPANT).items
                ] == [record.id]
                assert not list_requests(session, actor, 20, 0, WorkScope.PROCESSING).items
        record = world.act(
            record, world.manager, "approve", approval_id=str(record.approvals[0].id)
        ).request
        record = world.act(
            record, world.finance, "approve", approval_id=str(record.approvals[1].id)
        ).request
        with Session(world.engine) as session:
            assert [
                r.id
                for r in list_requests(session, world.finance, 20, 0, WorkScope.PROCESSING).items
            ] == [record.id]
            assert not list_requests(session, world.admin, 20, 0, WorkScope.PROCESSING).items

    def test_failed_history_rolls_back_submission(self, world: World) -> None:
        draft = world.create()

        def fail(session: Session, context: object, instances: object) -> None:
            if any(isinstance(obj, RequestEvent) and obj.sequence == 3 for obj in session.new):
                raise RuntimeError("Synthetic routing event failure")

        event.listen(Session, "before_flush", fail)
        try:
            with pytest.raises(RuntimeError, match="Synthetic routing"):
                world.act(draft, world.owner, "submit", data=submission())
        finally:
            event.remove(Session, "before_flush", fail)
        with Session(world.engine) as session:
            current = get_request(session, world.owner, draft.id)
            assert (
                current.version == 1 and current.structured_fields is None and not current.approvals
            )
            for table in (Approval, ApprovalCandidate, ApprovalDecision, MutationReceipt):
                assert session.scalar(select(func.count()).select_from(table)) == 0

    @pytest.mark.parametrize(
        "amount", [1.0, 1, "0", "-1", "NaN", "Infinity", "1e2", "1.001", "10000000000000000"]
    )
    def test_bad_money_rejected(self, world: World, amount: object) -> None:
        with pytest.raises(ValidationError):
            transition_adapter.validate_python(
                {
                    "action": "submit",
                    "expected_version": 1,
                    "reason": "Synthetic",
                    "data": {**submission(), "amount": amount},
                }
            )

    def test_typed_actions_and_date_order(self, world: World) -> None:
        for payload in (
            {"action": "submit", "data": {**submission("leave"), "end_date": "2026-10-01"}},
            {"action": "submit", "data": {**submission(), "currency": "USD"}},
            {"action": "approve", "approval_id": str(uuid4()), "data": {"bypass": True}},
            {"action": "process"},
            {"action": "assign"},
            {"action": "resolve"},
            {"action": "route"},
            {"action": "reopen", "resolved_at": "2026-10-14T00:00:00Z"},
            {"action": "reject", "reason": " "},
        ):
            with pytest.raises(ValidationError):
                transition_adapter.validate_python(
                    {"expected_version": 1, "reason": "Synthetic", **payload}
                )

    def test_out_of_order_steps_and_denied_service_actions(self, world: World) -> None:
        expense = world.submit(amount="100.01")
        for actor, action, data in (
            (world.finance, "approve", {"approval_id": str(expense.approvals[1].id)}),
            (world.finance, "process", {"reference": "Synthetic"}),
            (world.manager, "start", {}),
            (world.manager, "cancel", {}),
        ):
            with pytest.raises(DomainError):
                world.act(expense, actor, action, key=None, **data)
        service = world.create("service")
        for actor, action, data in (
            (world.owner, "triage", {}),
            (world.admin, "assign", {"assignee_id": str(world.colleague.user_id)}),
            (world.owner, "start", {}),
            (world.admin, "close", {}),
        ):
            with pytest.raises(DomainError):
                world.act(service, actor, action, key=None, **data)
        service = world.act(service, world.manager, "triage").request
        for user in (world.foreign.user_id, uuid4()):
            with pytest.raises(DomainError) as error:
                world.act(service, world.manager, "assign", assignee_id=str(user))
            assert error.value.status == 422
        service = world.act(
            service, world.manager, "assign", assignee_id=str(world.colleague.user_id)
        ).request
        with pytest.raises(DomainError):
            world.act(service, world.owner, "cancel")
        with Session(world.engine) as session:
            assert get_request(session, world.owner, expense.id).version == expense.version
            assert get_request(session, world.owner, service.id).version == service.version
            assert session.scalar(select(func.count()).select_from(ApprovalDecision)) == 0

    def test_submission_type_and_ownership(self, world: World) -> None:
        draft = world.create("leave")
        with pytest.raises(DomainError):
            world.act(draft, world.manager, "submit", data=submission("leave"))
        with pytest.raises(DomainError) as error:
            world.act(draft, world.owner, "submit", data=submission("expense"))
        assert error.value.status == 409
        with Session(world.engine) as session:
            assert get_request(session, world.owner, draft.id).version == 1
