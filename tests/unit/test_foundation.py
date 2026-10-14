from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import main
from app.domain.safety import (
    approval_actor_is_separate,
    cancellation_is_safe,
    expense_processing_role_is_eligible,
    leave_dates_are_ordered,
)
from app.domain.types import Role
from app.seed_fixtures import ExpenseFixture, load_fixtures


@pytest.mark.parametrize(
    "approved,effect,allowed",
    [(False, False, True), (True, False, False), (False, True, False), (True, True, False)],
)
def test_cancellation_safety(approved: bool, effect: bool, allowed: bool) -> None:
    assert cancellation_is_safe(finally_approved=approved, irreversible_effect=effect) is allowed


def test_self_approval_and_role_separation() -> None:
    employee, manager = uuid4(), uuid4()
    assert not approval_actor_is_separate(requester_id=employee, approver_id=employee)
    assert approval_actor_is_separate(requester_id=employee, approver_id=manager)
    assert not expense_processing_role_is_eligible(frozenset({Role.ADMIN, Role.MANAGER}))
    assert expense_processing_role_is_eligible(frozenset({Role.EMPLOYEE, Role.FINANCE}))


def test_leave_date_order() -> None:
    assert leave_dates_are_ordered(date(2026, 1, 1), date(2026, 1, 1))
    assert not leave_dates_are_ordered(date(2026, 1, 2), date(2026, 1, 1))


def test_canonical_fixtures_are_deterministic_typed_and_synthetic() -> None:
    first, second = load_fixtures(), load_fixtures()
    assert first == second
    assert len(first) == len({row.id for row in first}) == 100
    assert load_fixtures(10) == first[:10]
    assert {row.type for row in first[:10]} == {"service", "expense", "leave"}
    for row in first:
        assert row.created_at.utcoffset() is not None
        if isinstance(row, ExpenseFixture):
            assert isinstance(row.fields.amount, Decimal)
            assert row.fields.model_dump(mode="json")["amount"] == str(row.fields.amount)
    invalid = first[1].model_dump(mode="json")
    invalid["fields"]["amount"] = "not-money"
    with pytest.raises(ValidationError):
        ExpenseFixture.model_validate(invalid)


def test_health_independent_of_readiness_and_request_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        main,
        "dependency_checks",
        lambda: main.DependencyChecks(
            database="unavailable", migrations="unavailable", redis="unavailable"
        ),
    )
    with TestClient(main.app) as client:
        healthy = client.get("/health", headers={"X-Request-ID": "safe-id_123"})
        assert healthy.status_code == 200
        assert healthy.json() == {"status": "ok"}
        assert healthy.headers["X-Request-ID"] == "safe-id_123"
        unavailable = client.get("/ready")
        assert unavailable.status_code == 503
        assert unavailable.json()["status"] == "not_ready"
        assert "postgresql" not in unavailable.text
        rejected_id = client.get("/health", headers={"X-Request-ID": "x" * 65})
        assert rejected_id.headers["X-Request-ID"] != "x" * 65


@pytest.mark.parametrize(
    "database,migrations,redis,expected",
    [
        ("ok", "ok", "ok", 200),
        ("ok", "unavailable", "ok", 503),
        ("ok", "ok", "unavailable", 503),
        ("unavailable", "unavailable", "ok", 503),
    ],
)
def test_readiness_matrix(
    database: str, migrations: str, redis: str, expected: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    checks = main.DependencyChecks.model_validate(
        {"database": database, "migrations": migrations, "redis": redis}
    )
    monkeypatch.setattr(main, "dependency_checks", lambda: checks)
    with TestClient(main.app) as client:
        assert client.get("/ready").status_code == expected


def test_only_authorized_milestone_routes() -> None:
    paths = main.app.openapi()["paths"]
    assert set(paths) == {
        "/health",
        "/ready",
        "/requests",
        "/requests/{request_id}",
        "/auth/login",
        "/auth/logout",
        "/auth/me",
        "/approvals",
        "/requests/{request_id}/transitions",
        "/requests/{request_id}/revisions",
    }
    assert set(paths["/requests"]) == {"get", "post"}
    assert set(paths["/requests/{request_id}"]) == {"get"}
