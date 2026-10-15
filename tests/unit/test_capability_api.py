"""Read-only HTTP authority, bounded choices and additive transport contract."""

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.api.dependencies import authenticated_principal, database_session
from app.main import app
from tests.workflow_support import World, build_world


@pytest.fixture
def world(unit_engine: Engine) -> World:
    return build_world(unit_engine)


@pytest.fixture
def client(world: World) -> Iterator[TestClient]:
    def database() -> Iterator[Session]:
        with Session(world.engine) as session:
            yield session

    app.dependency_overrides[database_session] = database
    app.dependency_overrides[authenticated_principal] = lambda: world.owner
    try:
        with TestClient(app) as result:
            yield result
    finally:
        app.dependency_overrides.clear()


def test_capability_http_is_scoped_typed_and_uncached(client: TestClient, world: World) -> None:
    record = world.submit(amount="100.01")
    app.dependency_overrides[authenticated_principal] = lambda: world.manager
    result = client.get(f"/requests/{record.id}/capabilities")
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["expected_version"] == record.version
    assert {entry["action"] for entry in body["available_actions"]} == {
        "approve",
        "reject",
        "request_changes",
    }
    assert result.headers["cache-control"] == "no-store"
    assert "cookie" in {entry.strip().lower() for entry in result.headers["vary"].split(",")}
    assert result.headers["x-request-id"]
    queue = client.get("/work-queues/approvals?limit=1&offset=0")
    assert queue.status_code == 200, queue.text
    assert queue.json()["items"][0]["id"] == str(record.id)
    assert queue.headers["cache-control"] == "no-store"
    for actor in (world.admin, world.foreign):
        app.dependency_overrides[authenticated_principal] = lambda actor=actor: actor
        assert client.get(f"/requests/{record.id}/capabilities").status_code == 404
        assert client.get(f"/requests/{uuid4()}/capabilities").status_code == 404
        assert client.get("/work-queues/approvals").json()["items"] == []
    assert (
        client.post(f"/requests/{record.id}/capabilities", json={"action": "approve"}).status_code
        == 405
    )
    assert client.get("/users").status_code == 404
    assert client.get("/departments").status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        "/requests/options?limit=0",
        "/requests/options?offset=-1",
        "/work-queues/approvals?limit=101",
        "/work-queues/organization",
        "/requests/00000000-0000-4000-8000-000000000000/capabilities?limit=101",
    ],
)
def test_read_options_validate_bounds(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["detail"] == "Request input is invalid."


def test_options_scope_and_no_actor_overrides(client: TestClient, world: World) -> None:
    result = client.get("/requests/options?limit=1")
    assert result.status_code == 200, result.text
    assert result.json()["departments"]["items"][0]["id"] == str(world.department)
    record = world.submit()
    result = client.get(
        f"/requests/{record.id}/capabilities",
        headers={
            "X-User-ID": str(world.manager.user_id),
            "X-Organization-ID": str(world.foreign.organization_id),
        },
    )
    assert {entry["action"] for entry in result.json()["available_actions"]} == {"cancel"}


def test_capabilities_require_authentication_without_dependency_override(
    client: TestClient,
) -> None:
    app.dependency_overrides.pop(authenticated_principal)
    assert client.get("/requests/options").status_code == 401
    assert client.get("/work-queues/approvals").status_code == 401


def test_openapi_read_contract_has_no_actor_or_policy_inputs() -> None:
    document = app.openapi()
    for path in (
        "/requests/options",
        "/requests/{request_id}/capabilities",
        "/work-queues/{queue}",
    ):
        assert set(document["paths"][path]) == {"get"}
        names = {
            parameter["name"] for parameter in document["paths"][path]["get"].get("parameters", [])
        }
        assert names <= {"request_id", "queue", "limit", "offset"}


def test_capability_cache_headers_preserve_cors_variation(client: TestClient) -> None:
    response = client.get("/requests/options", headers={"Origin": "http://127.0.0.1:8000"})
    assert response.status_code == 200
    assert {entry.strip().lower() for entry in response.headers["vary"].split(",")} == {
        "cookie",
        "origin",
    }
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:8000"


def test_capability_candidate_identity_disclosure_matches_existing_detail_api(
    client: TestClient, world: World
) -> None:
    record = world.submit(amount="100.01")
    expected_candidates = {str(world.manager.user_id), str(world.finance.user_id)}
    for actor in (world.owner, world.manager, world.finance):
        app.dependency_overrides[authenticated_principal] = lambda actor=actor: actor
        detail = client.get(f"/requests/{record.id}")
        result = client.get(f"/requests/{record.id}/capabilities")
        assert detail.status_code == result.status_code == 200
        candidates = {value for step in detail.json()["approvals"] for value in step["candidates"]}
        assert candidates == expected_candidates
        participants = {person["id"] for person in result.json()["participants"]}
        assert participants == candidates | {str(world.owner.user_id)}
    for actor in (world.colleague, world.admin, world.foreign):
        app.dependency_overrides[authenticated_principal] = lambda actor=actor: actor
        assert client.get(f"/requests/{record.id}").status_code == 404
        assert client.get(f"/requests/{record.id}/capabilities").status_code == 404
