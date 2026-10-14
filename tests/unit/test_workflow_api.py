"""HTTP discriminators, scoped queues, pagination and error contract."""

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.api.dependencies import authenticated_principal, database_session
from app.main import app
from tests.workflow_support import World, build_world, submission


@pytest.fixture
def api_world(unit_engine: Engine) -> World:
    return build_world(unit_engine)


@pytest.fixture
def client(api_world: World) -> Iterator[TestClient]:
    def database_override() -> Iterator[Session]:
        with Session(api_world.engine) as session:
            yield session

    app.dependency_overrides[database_session] = database_override
    app.dependency_overrides[authenticated_principal] = lambda: api_world.owner
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def test_transition_http_and_actionable_queues(client: TestClient, api_world: World) -> None:
    world = api_world
    draft = world.create()
    body = {
        "action": "submit",
        "expected_version": draft.version,
        "reason": "Synthetic",
        "data": submission(amount="100.01"),
    }
    response = client.post(
        f"/requests/{draft.id}/transitions", json=body, headers={"Idempotency-Key": str(uuid4())}
    )
    assert response.status_code == 200, response.text
    record = response.json()["request"]
    assert record["status"] == "MANAGER_REVIEW" and record["version"] == 3
    app.dependency_overrides[authenticated_principal] = lambda: world.finance
    assert client.get("/approvals").json()["items"] == []
    app.dependency_overrides[authenticated_principal] = lambda: world.manager
    queue = client.get("/approvals?limit=1&offset=0").json()
    assert [a["id"] for a in queue["items"]] == [record["approvals"][0]["id"]]
    assert client.get("/approvals?offset=1").json()["items"] == []
    decision = {
        "action": "approve",
        "expected_version": 3,
        "reason": "Synthetic approval",
        "approval_id": record["approvals"][0]["id"],
    }
    response = client.post(
        f"/requests/{draft.id}/transitions",
        json=decision,
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 200, response.text
    assert response.json()["outcome"]["decision_id"]
    assert client.get("/approvals").json()["items"] == []
    app.dependency_overrides[authenticated_principal] = lambda: world.finance
    assert [a["id"] for a in client.get("/approvals").json()["items"]] == [
        record["approvals"][1]["id"]
    ]
    app.dependency_overrides[authenticated_principal] = lambda: world.admin
    assert client.get(f"/requests/{draft.id}").status_code == 404
    assert client.get("/approvals").json()["items"] == []
    assert client.get("/requests?scope=participant").json()["items"] == []


def test_transition_validation_and_problem_bodies(client: TestClient, api_world: World) -> None:
    draft = api_world.create()
    url = f"/requests/{draft.id}/transitions"
    body = {"action": "submit", "expected_version": 1, "reason": "Synthetic", "data": submission()}
    for invalid in (
        {**body, "data": {**submission(), "amount": 1.0}},
        {**body, "actor_id": str(api_world.manager.user_id)},
        {**body, "data": {**submission(), "policy_id": str(uuid4())}},
        {**body, "action": "route"},
        {**body, "expected_version": 0},
    ):
        result = client.post(url, json=invalid, headers={"Idempotency-Key": str(uuid4())})
        assert result.status_code == 422
        assert result.headers["content-type"] == "application/problem+json"
        assert result.headers["x-request-id"]
        assert result.json()["detail"] == "Request input is invalid."
    assert client.post(url, json=body).status_code == 422
    assert client.patch(f"/requests/{draft.id}", json={"status": "APPROVED"}).status_code == 405
    assert client.get("/approvals?limit=101").status_code == 422
    assert client.get("/requests?scope=organization").status_code == 422


def test_triage_and_assigned_lists_filter_before_pagination(
    client: TestClient, api_world: World
) -> None:
    world = api_world
    record = world.create("service")
    world.create("expense")
    app.dependency_overrides[authenticated_principal] = lambda: world.manager
    assert [r["id"] for r in client.get("/requests?scope=triage&limit=1").json()["items"]] == [
        str(record.id)
    ]
    record = world.act(record, world.manager, "triage").request
    record = world.act(
        record, world.manager, "assign", assignee_id=str(world.colleague.user_id)
    ).request
    app.dependency_overrides[authenticated_principal] = lambda: world.colleague
    assert [r["id"] for r in client.get("/requests?scope=assigned").json()["items"]] == [
        str(record.id)
    ]
    assert client.get("/requests?scope=triage").json()["items"] == []


def test_openapi_actions_and_money_are_discriminated() -> None:
    document = app.openapi()
    body = document["paths"]["/requests/{request_id}/transitions"]["post"]["requestBody"][
        "content"
    ]["application/json"]["schema"]
    assert body["discriminator"]["propertyName"] == "action"
    assert len(body["oneOf"]) == 13
    assert (
        document["components"]["schemas"]["ExpenseSubmission"]["properties"]["amount"]["type"]
        == "string"
    )


def test_revision_http_contract(client: TestClient, api_world: World) -> None:
    record = api_world.submit(amount="100.01")
    url = f"/requests/{record.id}/transitions"
    body: dict[str, object] = {
        "action": "request_changes",
        "expected_version": record.version,
        "reason": "Explain the vendor",
        "approval_id": str(record.approvals[0].id),
    }
    app.dependency_overrides[authenticated_principal] = lambda: api_world.manager
    result = client.post(url, json=body, headers={"Idempotency-Key": str(uuid4())})
    assert result.status_code == 200, result.text
    assert result.json()["request"]["correction"]["approval_id"] == str(record.approvals[0].id)
    assert client.get("/approvals").json()["items"] == []
    version = result.json()["request"]["version"]
    app.dependency_overrides[authenticated_principal] = lambda: api_world.owner
    body = {
        "action": "revise",
        "expected_version": version,
        "reason": "Corrected vendor",
        "data": {**submission(), "vendor": "Revised vendor"},
        "clarification": "Confirmed vendor identity",
    }
    for invalid in (
        {**body, "status": "APPROVED"},
        {**body, "raw_text": "Rewrite intake"},
        {**body, "data": {**submission(), "department_id": str(uuid4())}},
        {**body, "clarification": " "},
        {**body, "clarification": "x" * 20001},
        {**body, "data": {**submission(), "amount": 1.5}},
    ):
        response = client.post(url, json=invalid, headers={"Idempotency-Key": str(uuid4())})
        assert response.status_code == 422
        assert response.json()["detail"] == "Request input is invalid."
    result = client.post(url, json=body, headers={"Idempotency-Key": str(uuid4())})
    assert result.status_code == 200, result.text
    detail = result.json()["request"]
    assert detail["structured_fields"]["vendor"] == "Synthetic vendor"
    assert detail["proposed_revision"]["fields"]["vendor"] == "Revised vendor"
    body = {
        "action": "resubmit",
        "expected_version": detail["version"],
        "reason": "Ready for review",
        "revision_id": detail["proposed_revision"]["id"],
    }
    result = client.post(url, json=body, headers={"Idempotency-Key": str(uuid4())})
    assert result.status_code == 200, result.text
    assert result.json()["request"]["structured_fields"]["vendor"] == "Revised vendor"
    history = client.get(f"/requests/{record.id}/revisions?limit=1").json()
    assert len(history["items"]) == 1 and history["submissions"][0]["sequence"] == 2
    assert (
        client.get(f"/requests/{record.id}/revisions?offset=1").json()["items"][0]["kind"]
        == "proposed"
    )
    app.dependency_overrides[authenticated_principal] = lambda: api_world.admin
    assert client.get(f"/requests/{record.id}/revisions").status_code == 404
