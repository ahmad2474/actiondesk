"""Capability/security acceptance shared by SQLite unit and live PostgreSQL adapters."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.db.models import (
    ActiveApprovalPolicy,
    Base,
    EmployeeManager,
    Organization,
    RoleAssignment,
    User,
)
from app.domain.errors import DomainError
from app.domain.identity import Principal
from app.domain.types import Role
from app.schemas.capabilities import QueueKind, RequestCapabilities
from app.schemas.core import RequestDetail
from app.services.capabilities import creation_options, get_capabilities, work_queue
from tests.lifecycle_cases import approved, configure_reopen, resolved
from tests.workflow_support import World, add_actor, submission


def capabilities(world: World, actor: Principal, record: RequestDetail) -> RequestCapabilities:
    with Session(world.engine) as session:
        return get_capabilities(session, actor, record.id)


def names(result: RequestCapabilities) -> set[str]:
    return {item.action.value for item in result.available_actions}


def queue_ids(
    world: World, actor: Principal, kind: QueueKind, limit: int = 20, offset: int = 0
) -> list[UUID]:
    with Session(world.engine) as session:
        return [item.id for item in work_queue(session, actor, kind, limit, offset).items]


class CapabilityCases:
    def test_draft_owner_and_current_review_actions(self, world: World) -> None:
        draft = world.create()
        result = capabilities(world, world.owner, draft)
        assert names(result) == {"submit", "cancel"}
        assert result.expected_version == draft.version
        for actor in (world.manager, world.admin, world.foreign):
            with pytest.raises(DomainError) as caught:
                capabilities(world, actor, draft)
            assert caught.value.status == 404
        record = world.act(draft, world.owner, "submit", data=submission(amount="100.01")).request
        assert names(capabilities(world, world.owner, record)) == {"cancel"}
        result = capabilities(world, world.manager, record)
        assert names(result) == {"approve", "reject", "request_changes"}
        assert {item.approval_id for item in result.available_actions} == {record.approvals[0].id}
        assert names(capabilities(world, world.finance, record)) == set()
        assert queue_ids(world, world.finance, QueueKind.APPROVALS) == []
        assert queue_ids(world, world.manager, QueueKind.APPROVALS) == [record.id]
        record = world.act(
            record, world.manager, "approve", approval_id=str(record.approvals[0].id)
        ).request
        assert names(capabilities(world, world.manager, record)) == set()
        assert names(capabilities(world, world.finance, record)) == {
            "approve",
            "reject",
            "request_changes",
        }

    @pytest.mark.parametrize("change", ["role", "future_role", "inactive", "relationship"])
    def test_current_eligibility_and_snapshot_exclusion(self, world: World, change: str) -> None:
        record = world.submit()
        replacement = add_actor(
            world.engine, world.owner, world.department, (Role.EMPLOYEE, Role.MANAGER)
        )
        with Session(world.engine) as session, session.begin():
            role = session.get(
                RoleAssignment, (world.owner.organization_id, world.manager.user_id, Role.MANAGER)
            )
            assert role
            if change == "role":
                role.revoked_at = datetime.now(UTC)
            elif change == "future_role":
                role.granted_at = datetime.now(UTC) + timedelta(days=1)
            elif change == "inactive":
                user = session.get(User, world.manager.user_id)
                assert user
                user.status = "inactive"
            else:
                relation = session.get(
                    EmployeeManager, (world.owner.organization_id, world.owner.user_id)
                )
                assert relation
                relation.manager_id = replacement.user_id
        with pytest.raises(DomainError) as caught:
            capabilities(world, world.manager, record)
        assert caught.value.status == (401 if change == "inactive" else 404)
        if change != "inactive":
            assert queue_ids(world, world.manager, QueueKind.APPROVALS) == []
        with pytest.raises(DomainError) as caught:
            capabilities(world, replacement, record)
        assert caught.value.status == 404
        assert names(capabilities(world, world.owner, record)) == {"cancel"}

    def test_multi_role_requester_never_reviews_or_processes(self, world: World) -> None:
        with Session(world.engine) as session, session.begin():
            session.add_all(
                [
                    RoleAssignment(
                        organization_id=world.owner.organization_id,
                        user_id=world.owner.user_id,
                        role=role,
                    )
                    for role in (Role.MANAGER, Role.FINANCE, Role.ADMIN)
                ]
            )
        record = world.submit(amount="100.01")
        assert names(capabilities(world, world.owner, record)) == {"cancel"}
        assert queue_ids(world, world.owner, QueueKind.APPROVALS) == []
        record = world.act(
            record, world.manager, "approve", approval_id=str(record.approvals[0].id)
        ).request
        record = world.act(
            record, world.finance, "approve", approval_id=str(record.approvals[1].id)
        ).request
        assert names(capabilities(world, world.owner, record)) == {"request_reversal"}
        assert queue_ids(world, world.owner, QueueKind.FINANCE_PROCESSING) == []
        assert names(capabilities(world, world.finance, record)) == {"process", "request_reversal"}

    def test_nonrequester_multi_role_steps_and_processing_are_separate(self, world: World) -> None:
        with Session(world.engine) as session, session.begin():
            session.add_all(
                [
                    RoleAssignment(
                        organization_id=world.owner.organization_id,
                        user_id=world.manager.user_id,
                        role=role,
                    )
                    for role in (Role.FINANCE, Role.ADMIN)
                ]
            )
        record = world.submit(amount="100.01")
        for step in (0, 1):
            result = capabilities(world, world.manager, record)
            assert names(result) == {"approve", "reject", "request_changes"}
            assert result.available_actions[0].approval_id == record.approvals[step].id
            record = world.act(
                record, world.manager, "approve", approval_id=str(record.approvals[step].id)
            ).request
        assert "process" in names(capabilities(world, world.manager, record))
        record = world.act(
            record, world.manager, "process", reference="Synthetic processing"
        ).request
        assert names(capabilities(world, world.manager, record)) == set()
        assert names(capabilities(world, world.owner, record)) == set()

    @pytest.mark.parametrize("amount", ["99.99", "100.00", "100.01"])
    def test_revision_resubmit_rechecks_policy_candidates_and_current_step(
        self, world: World, amount: str
    ) -> None:
        record = world.submit()
        old_id = record.approvals[0].id
        record = world.act(
            record, world.manager, "request_changes", approval_id=str(old_id)
        ).request
        assert names(capabilities(world, world.owner, record)) == {"revise", "cancel"}
        record = world.act(
            record,
            world.owner,
            "revise",
            data=submission(amount=amount),
            clarification="Updated explanation",
        ).request
        result = capabilities(world, world.owner, record)
        assert names(result) == {"revise", "resubmit", "cancel"}
        assert record.proposed_revision
        assert (
            next(item for item in result.available_actions if item.action == "resubmit").revision_id
            == record.proposed_revision.id
        )
        with Session(world.engine) as session, session.begin():
            role = session.get(
                RoleAssignment, (world.owner.organization_id, world.finance.user_id, Role.FINANCE)
            )
            assert role
            role.revoked_at = datetime.now(UTC)
        result = capabilities(world, world.owner, record)
        assert ("resubmit" in names(result)) == (amount != "100.01")
        if amount == "100.01":
            assert result.blocking and result.blocking[0].code == "not_ready"
            assert "candidate" not in result.model_dump_json()
        else:
            record = world.act(
                record, world.owner, "resubmit", revision_id=str(record.proposed_revision.id)
            ).request
            result = capabilities(world, world.manager, record)
            assert (
                next(
                    item for item in result.available_actions if item.action == "approve"
                ).approval_id
                != old_id
            )

    def test_missing_policy_blocks_without_internal_information(self, world: World) -> None:
        record = world.create()
        with Session(world.engine) as session, session.begin():
            selected = session.get(ActiveApprovalPolicy, (world.owner.organization_id, record.type))
            assert selected
            session.delete(selected)
        result = capabilities(world, world.owner, record)
        assert names(result) == {"cancel"}
        assert result.blocking[0].code == "not_ready"
        serialized = result.model_dump_json()
        assert "policy_id" not in serialized and "finance_threshold" not in serialized

    def test_reversal_independence_and_current_final_step(self, world: World) -> None:
        alternate = add_actor(
            world.engine, world.owner, world.department, (Role.EMPLOYEE, Role.FINANCE)
        )
        record = approved(world, amount="100.01")
        assert names(capabilities(world, world.manager, record)) == set()
        record = world.act(record, world.finance, "request_reversal", intent="correct").request
        assert names(capabilities(world, world.finance, record)) == set()
        assert names(capabilities(world, world.owner, record)) == set()
        assert names(capabilities(world, alternate, record)) == {
            "approve_reversal",
            "reject_reversal",
        }
        assert queue_ids(world, world.finance, QueueKind.REVERSALS) == []
        assert queue_ids(world, alternate, QueueKind.REVERSALS) == [record.id]
        with Session(world.engine) as session:
            queue = work_queue(session, world.finance, QueueKind.FINANCE_PROCESSING, 20, 0)
        assert [item.id for item in queue.items] == [record.id]
        assert queue.items[0].blocking[0].code == "reversal_review"
        assert "process" not in {item.action.value for item in queue.items[0].available_actions}
        assert record.active_reversal
        record = world.act(
            record,
            alternate,
            "approve_reversal",
            reversal_request_id=str(record.active_reversal.id),
        ).request
        assert names(capabilities(world, world.owner, record)) == {"create_correction"}
        assert record.active_reversal
        world.act(
            record,
            world.owner,
            "create_correction",
            reversal_request_id=str(record.active_reversal.id),
        )
        assert names(capabilities(world, world.owner, record)) == set()

    def test_single_approver_initiation_remains_blocked(self, world: World) -> None:
        record = approved(world)
        record = world.act(record, world.manager, "request_reversal", intent="withdraw").request
        assert names(capabilities(world, world.manager, record)) == set()
        assert names(capabilities(world, world.owner, record)) == set()
        assert queue_ids(world, world.manager, QueueKind.REVERSALS) == []

    def test_leave_timezone_boundary_acceptance_vs_denial(self, world: World) -> None:
        record = approved(world, "leave")
        with Session(world.engine) as session, session.begin():
            org = session.get(Organization, world.owner.organization_id)
            assert org
            org.timezone = "Asia/Karachi"
        assert record.structured_fields
        start = (
            datetime.fromisoformat(str(record.structured_fields["start_date"]))
            .replace(tzinfo=ZoneInfo("Asia/Karachi"))
            .astimezone(UTC)
        )
        with patch(
            "app.services.capabilities.observed_at", return_value=start - timedelta(microseconds=1)
        ):
            assert names(capabilities(world, world.owner, record)) == {"request_reversal"}
        with patch("app.services.capabilities.observed_at", return_value=start):
            assert names(capabilities(world, world.owner, record)) == set()
        record = world.act(record, world.owner, "request_reversal", intent="withdraw").request
        with patch("app.services.capabilities.observed_at", return_value=start):
            assert names(capabilities(world, world.manager, record)) == {"reject_reversal"}
            assert queue_ids(world, world.manager, QueueKind.REVERSALS) == [record.id]

    def test_service_assignment_choices_and_work_cycle(self, world: World) -> None:
        record = world.create("service")
        assert names(capabilities(world, world.owner, record)) == {"cancel"}
        assert names(capabilities(world, world.manager, record)) == {"triage"}
        assert names(capabilities(world, world.admin, record)) == {"triage"}
        record = world.act(record, world.manager, "triage").request
        result = capabilities(world, world.manager, record)
        assert names(result) == {"assign"} and result.assignee_choices
        assert world.colleague.user_id in {item.id for item in result.assignee_choices.items}
        assert world.foreign.user_id not in {item.id for item in result.assignee_choices.items}
        assert capabilities(world, world.owner, record).assignee_choices is None
        record = world.act(
            record, world.manager, "assign", assignee_id=str(world.colleague.user_id)
        ).request
        assert names(capabilities(world, world.colleague, record)) == {"start"}
        assert names(capabilities(world, world.manager, record)) == {"cancel"}
        assert names(capabilities(world, world.owner, record)) == set()
        record = world.act(record, world.colleague, "start").request
        assert names(capabilities(world, world.colleague, record)) == {"resolve"}
        assert names(capabilities(world, world.admin, record)) == set()
        record = world.act(record, world.colleague, "resolve", resolution="Repaired").request
        assert names(capabilities(world, world.owner, record)) == {"close"}
        configure_reopen(world)
        assert names(capabilities(world, world.owner, record)) == {"close", "reopen"}
        assert names(capabilities(world, world.manager, record)) == {"reopen"}
        assert names(capabilities(world, world.admin, record)) == {"close", "reopen"}
        record = world.act(record, world.owner, "close").request
        assert names(capabilities(world, world.owner, record)) == set()
        assert queue_ids(world, world.manager, QueueKind.SERVICE_WORK) == []

    def test_reopen_inclusive_expiry_and_retained_assignee(self, world: World) -> None:
        configure_reopen(world)
        record = resolved(world)
        assert record.current_resolution
        expiry = record.current_resolution.at + timedelta(days=7)
        with patch("app.services.capabilities.observed_at", return_value=expiry):
            assert "reopen" in names(capabilities(world, world.owner, record))
        with patch(
            "app.services.capabilities.observed_at", return_value=expiry + timedelta(microseconds=1)
        ):
            assert names(capabilities(world, world.owner, record)) == {"close"}
        with Session(world.engine) as session, session.begin():
            user = session.get(User, world.colleague.user_id)
            assert user
            user.status = "inactive"
        assert names(capabilities(world, world.owner, record)) == {"close"}

    def test_names_and_options_never_enumerate_unrelated_or_foreign_users(
        self, world: World
    ) -> None:
        unrelated = add_actor(world.engine, world.owner, world.department, (Role.EMPLOYEE,))
        record = world.submit()
        result = capabilities(world, world.owner, record)
        assert {person.id for person in result.participants} == {
            world.owner.user_id,
            world.manager.user_id,
        }
        encoded = result.model_dump_json()
        for hidden in (unrelated, world.finance, world.admin, world.foreign):
            assert str(hidden.user_id) not in encoded
        assert "email" not in encoded and "roles" not in encoded and "policy" not in encoded
        with Session(world.engine) as session:
            options = creation_options(session, world.owner, 1, 0)
        assert {item.id for item in options.departments.items} == {world.department}
        assert "users" not in options.model_dump_json()
        assert options.organization_timezone == "UTC"
        for kind in QueueKind:
            assert queue_ids(world, world.foreign, kind) == []

    def test_reads_do_not_write_or_capture_compatibility_evidence(self, world: World) -> None:
        record = approved(world)
        statements: list[str] = []

        def observe(connection, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
            statements.append(statement.upper())

        with Session(world.engine) as session:
            before = {
                table.name: session.scalar(select(func.count()).select_from(table))
                for table in Base.metadata.sorted_tables
            }
        event.listen(world.engine, "before_cursor_execute", observe)
        try:
            capabilities(world, world.owner, record)
            for kind in QueueKind:
                queue_ids(world, world.manager, kind)
            with Session(world.engine) as session:
                creation_options(session, world.owner)
        finally:
            event.remove(world.engine, "before_cursor_execute", observe)
        assert not any(
            statement.lstrip().startswith(("INSERT", "UPDATE", "DELETE"))
            for statement in statements
        )
        assert not any(
            "FOR UPDATE" in statement or "FOR SHARE" in statement for statement in statements
        )
        with Session(world.engine) as session:
            after = {
                table.name: session.scalar(select(func.count()).select_from(table))
                for table in Base.metadata.sorted_tables
            }
        assert before == after

    def test_stale_capability_is_not_a_mutation_grant(self, world: World) -> None:
        record = world.submit()
        snapshot = capabilities(world, world.manager, record)
        world.act(record, world.manager, "request_changes", approval_id=str(record.approvals[0].id))
        with pytest.raises(DomainError) as caught:
            world.act(
                record,
                world.manager,
                "approve",
                approval_id=str(snapshot.available_actions[0].approval_id),
            )
        assert caught.value.status == 409
        result = capabilities(world, world.owner, record)
        assert result.expected_version > snapshot.expected_version
        assert names(result) == {"revise", "cancel"}

    def test_queue_pagination_and_summary_exclude_unrelated_sensitive_data(
        self, world: World
    ) -> None:
        withdrawn = world.submit()
        world.act(withdrawn, world.owner, "cancel")
        first, second = world.submit(amount="99.99"), world.submit(amount="100.01")
        assert queue_ids(world, world.manager, QueueKind.APPROVALS, 1, 0) == [first.id]
        assert queue_ids(world, world.manager, QueueKind.APPROVALS, 1, 1) == [second.id]
        assert queue_ids(world, world.manager, QueueKind.APPROVALS, 1, 2) == []
        with Session(world.engine) as session:
            queue = work_queue(session, world.manager, QueueKind.APPROVALS, 1, 0)
        assert queue.has_more and queue.items[0].amount == "99.99"
        assert queue.items[0].requester.id == world.owner.user_id
        encoded = queue.model_dump_json()
        assert all(
            key not in encoded
            for key in ("raw_text", "purpose", "email", "candidates", "finance_threshold")
        )

    def test_resubmission_resolves_new_manager_and_old_nomination_loses_access(
        self, world: World
    ) -> None:
        record = world.submit(amount="100.01")
        record = world.act(
            record, world.manager, "approve", approval_id=str(record.approvals[0].id)
        ).request
        record = world.act(
            record, world.finance, "request_changes", approval_id=str(record.approvals[1].id)
        ).request
        record = world.act(
            record,
            world.owner,
            "revise",
            data=submission(amount="100.01"),
            clarification="Explanation-only clarification",
        ).request
        replacement = add_actor(
            world.engine, world.owner, world.department, (Role.EMPLOYEE, Role.MANAGER)
        )
        with Session(world.engine) as session, session.begin():
            relation = session.get(
                EmployeeManager, (world.owner.organization_id, world.owner.user_id)
            )
            assert relation
            relation.manager_id = replacement.user_id
        assert "resubmit" in names(capabilities(world, world.owner, record))
        assert record.proposed_revision
        record = world.act(
            record, world.owner, "resubmit", revision_id=str(record.proposed_revision.id)
        ).request
        result = capabilities(world, replacement, record)
        assert names(result) == {"approve", "reject", "request_changes"}
        # Earlier decision authors retain only current-role audit visibility, never an action.
        assert names(capabilities(world, world.manager, record)) == set()
        assert queue_ids(world, world.manager, QueueKind.APPROVALS) == []
        assert queue_ids(world, replacement, QueueKind.APPROVALS) == [record.id]

    @pytest.mark.parametrize("change", ["inactive", "role"])
    def test_assignee_choices_recheck_current_user_and_role(
        self, world: World, change: str
    ) -> None:
        record = world.act(world.create("service"), world.manager, "triage").request
        with Session(world.engine) as session, session.begin():
            if change == "inactive":
                user = session.get(User, world.colleague.user_id)
                assert user
                user.status = "inactive"
            else:
                role = session.get(
                    RoleAssignment,
                    (world.owner.organization_id, world.colleague.user_id, Role.EMPLOYEE),
                )
                assert role
                role.revoked_at = datetime.now(UTC)
        result = capabilities(world, world.manager, record)
        assert result.assignee_choices
        assert world.colleague.user_id not in {entry.id for entry in result.assignee_choices.items}

    def test_superseded_unacted_finance_nominee_loses_visibility(self, world: World) -> None:
        record = world.submit(amount="100.01")
        assert capabilities(world, world.finance, record)
        record = world.act(
            record, world.manager, "request_changes", approval_id=str(record.approvals[0].id)
        ).request
        record = world.act(
            record,
            world.owner,
            "revise",
            data=submission(amount="99.99"),
            clarification="Reduced scope",
        ).request
        assert record.proposed_revision
        record = world.act(
            record, world.owner, "resubmit", revision_id=str(record.proposed_revision.id)
        ).request
        with pytest.raises(DomainError) as caught:
            capabilities(world, world.finance, record)
        assert caught.value.status == 404
        assert world.finance.user_id not in {
            entry.id for entry in capabilities(world, world.owner, record).participants
        }

    @pytest.mark.parametrize(
        "viewer",
        [
            "owner",
            "manager",
            "future_finance",
            "processing_finance",
            "held_finance",
            "processed_finance",
            "decision_author",
            "correction_author",
            "service_owner",
            "service_assignee",
            "service_manager",
            "service_admin",
        ],
    )
    def test_candidate_names_resolve_only_identities_already_visible_in_detail_and_history(
        self, world: World, viewer: str
    ) -> None:
        from app.services.requests import get_request, list_revisions

        actor = world.owner
        if viewer.startswith("service_"):
            record = resolved(world)
            actor = {
                "service_owner": world.owner,
                "service_assignee": world.colleague,
                "service_manager": world.manager,
                "service_admin": world.admin,
            }[viewer]
        elif viewer in {"processing_finance", "held_finance", "processed_finance"}:
            # Finance can view this request without ever being nominated for approval.
            record = approved(world, amount="100.00")
            actor = world.finance
            if viewer == "held_finance":
                record = world.act(
                    record, world.owner, "request_reversal", intent="withdraw"
                ).request
            elif viewer == "processed_finance":
                record = world.act(record, world.finance, "process", reference="Synthetic").request
        elif viewer in {"decision_author", "correction_author"}:
            record = world.submit(amount="100.01")
            record = world.act(
                record, world.manager, "approve", approval_id=str(record.approvals[0].id)
            ).request
            record = world.act(
                record, world.finance, "request_changes", approval_id=str(record.approvals[1].id)
            ).request
            record = world.act(
                record,
                world.owner,
                "revise",
                data=submission(amount="99.99"),
                clarification="Reduced scope",
            ).request
            replacement = add_actor(
                world.engine, world.owner, world.department, (Role.EMPLOYEE, Role.MANAGER)
            )
            with Session(world.engine) as session, session.begin():
                relationship = session.get(
                    EmployeeManager, (world.owner.organization_id, world.owner.user_id)
                )
                assert relationship
                relationship.manager_id = replacement.user_id
            assert record.proposed_revision
            record = world.act(
                record, world.owner, "resubmit", revision_id=str(record.proposed_revision.id)
            ).request
            actor = world.manager if viewer == "decision_author" else world.finance
        else:
            record = world.submit(amount="100.01")
            actor = {
                "owner": world.owner,
                "manager": world.manager,
                "future_finance": world.finance,
            }[viewer]

        # Read through the established services, not the capability implementation's
        # candidate query. These paths existed before 6B and have identical visibility.
        with Session(world.engine) as session:
            detail = get_request(session, actor, record.id)
            history = list_revisions(session, actor, record.id, 100, 0)
        current_ids = {candidate for step in detail.approvals for candidate in step.candidates}
        if detail.current_submission_sequence is not None:
            current_history = next(
                item
                for item in history.submissions
                if item.sequence == detail.current_submission_sequence
            )
            assert current_ids == {
                candidate for step in current_history.approvals for candidate in step.candidates
            }
        if viewer in {
            "processing_finance",
            "held_finance",
            "processed_finance",
            "decision_author",
            "correction_author",
        }:
            assert actor.user_id not in current_ids
        if viewer.startswith("service_"):
            assert current_ids == set()

        already_visible_ids = {detail.created_by, *current_ids}
        already_visible_ids.update(
            item.actor_id for item in detail.status_history if item.actor_id is not None
        )
        already_visible_ids.update(
            value for value in (detail.assigned_to, detail.processed_by) if value is not None
        )
        result = capabilities(world, actor, record)
        labels = {person.id: person.name for person in result.participants}
        assert current_ids <= labels.keys()
        assert labels.keys() <= already_visible_ids
        assert result.expected_version == detail.version
        assert all(set(person.model_dump()) == {"id", "name"} for person in result.participants)
        assert world.foreign.user_id not in labels
