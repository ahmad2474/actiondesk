# Phase 1 milestone 1: domain and persistence foundation

Status: implemented within the authorized scope; real PostgreSQL verification is blocked in this execution environment. This is not completion of Phase 1. No commit was made.

## Scope and specification

Both PRDs were extracted with `pdftotext -layout` and reviewed. PRD v1.1 Sections 2, 4, 9, 10, 16.1 and 16.6–16.7 govern identity, tenant scoping, history, typed APIs, and phase boundaries. The user's milestone authorization overrides the earlier Phase 0 stop instruction. No approval, processing, cancellation/reversal/reopening, AI, notification, frontend workflow, worker, or deployment feature is added.

Most core entities already existed in the accepted Phase 0 schema. They are reused rather than duplicated:

| Concept | Persistence |
| --- | --- |
| Users and departments | Existing tenant-scoped `users` and `departments`, with organization/email and organization/department-name uniqueness. |
| Roles | New `roles` catalog keyed by the central enum: employee, manager, finance, admin. No role administration endpoint. |
| User roles | Existing `role_assignments` is the separate user-role relation. Its organization/user/role primary key permits multiple roles; a new FK references the catalog. Existing grant/revocation timestamps remain. |
| Explicit managers | Existing `employee_managers` and `department_managers`, with organization-qualified, manager-role-qualified FKs. |
| Requests | Existing requester (`created_by`) and organization relationships; `department_id` is now required. A nullable UUID creation retry key has uniqueness per organization/requester/key. Historical fixtures have no retry key. |
| Status history | Existing append-only `request_events`, with request, actor, old/new state, reason, timestamp, and unique organization/request/sequence. This is the status-history foundation, not a duplicate audit table. |

`0002_request_foundation` extends the original migration. A deferred PostgreSQL constraint trigger checks that newly inserted requests have history matching their version/status and that any status/version change advances the version by one and has a matching old/new-state event. The existing trigger rejects history updates/deletes. The migration refuses missing departments or inconsistent current history rather than inventing a backfill or resetting existing records.

## Initial state and APIs

`initial_request_status` is central and deterministic: service → `SUBMITTED`; expense/leave → `DRAFT`, consistent with PRD Section 4. This milestone adds no new request states. The existing full enum remains for historical compatibility; no later transitions or approval-specific states are entered by the new creation service.

- `POST /requests`: typed requester, department, manual type, title, description; UUID `Idempotency-Key` header required. Status, organization, assignee and other extra input fields are forbidden. Request and initial history are committed atomically, with actor and timestamp recorded. The same key/input returns the same request without duplicate history; conflicting input returns 409. No outbox jobs or queue tasks are created.
- `GET /requests/{request_id}`: requester-owned detail and ordered status history; invisible or absent records return the same 404.
- `GET /requests`: requester-owned results, ordered by creation timestamp and UUID; default limit 20, maximum 100, nonnegative offset. No organization-wide manager/admin visibility shortcut.
- User/department create/read and status-history schemas are defined; no generic user/department management endpoints are added. User reads omit credentials and include the role set.

Errors use sanitized RFC 7807-style bodies and the existing request-ID middleware. Invalid input is not echoed in validation errors. OpenAPI and TypeScript declarations are generated using `openapi-typescript`.

## Authentication boundary and deferred decisions

The repository has no login/session verifier, and none was specified in this milestone's endpoint slice. This ambiguity was raised before implementation. The conservative implementation denies all production request API calls with 401 until a verified identity dependency is implemented. It never accepts a user/organization ID header or selects a seeded individual as an authentication substitute. Tests explicitly override that dependency; there is no environment toggle that enables test identities in the application.

Behind that boundary, services verify that the trusted user exists, is active in the trusted organization, and has an active granted role. Creation is only for that user. Unknown/mismatched requester input receives 403 without revealing whether another user exists; a missing/inactive trusted requester receives 401. Missing/foreign departments receive 422. Every request/history read is tenant-scoped and requester-owned. Broader manager/admin confidential-data visibility and usable secure login require a later approved milestone.

## Checks actually executed

Commands run from the repository root with the existing locked development dependencies; no new infrastructure or dependencies were introduced.

| Exact command | Result |
| --- | --- |
| `UV_CACHE_DIR=.cache/uv uv run --frozen ruff check apps tests scripts` | Passed. |
| `UV_CACHE_DIR=.cache/uv uv run --frozen ruff format --check apps tests scripts` | Passed; 36 files formatted. |
| `UV_CACHE_DIR=.cache/uv uv run --frozen mypy` | Passed; 36 source files. A duplicate test-module filename found in the first attempt was corrected before rerunning. |
| `UV_CACHE_DIR=.cache/uv uv run --frozen pytest tests/unit -q` | Passed; 35 tests, one upstream Starlette/httpx deprecation warning. |
| `make contracts` | Passed; regenerated actual FastAPI OpenAPI and TypeScript declarations. |
| `make contracts-check` | Passed; no contract drift. |
| `node --test tests/contracts.test.mjs` | Passed; 7 tests, zero skipped, including changed-schema and tampered-artifact drift detection. |
| `npm run typecheck --workspace @actiondesk/contracts` | Passed again after the final contract regeneration. |
| `npm run typecheck` | Passed; contracts, web and check configuration types. Next's incidental regenerated `next-env.d.ts` was restored to its original contents; no frontend source change is retained. |
| `make compose-check` | Passed; base and local override configuration. Neither Compose file was modified. |
| `UV_CACHE_DIR=.cache/uv uv run --frozen alembic upgrade head --sql > /tmp/actiondesk-phase1-m1-migrations.sql` | Passed offline SQL generation through the new revision; this does not verify execution against PostgreSQL. |
| `UV_CACHE_DIR=.cache/uv uv run --frozen pytest tests/integration -q --maxfail=1 > /tmp/actiondesk-phase1-m1-integration.log 2>&1` | Blocked at the first database fixture; connection to localhost:5432 failed with `Operation not permitted`. No database test passed. |
| `UV_CACHE_DIR=.cache/uv uv run --frozen pytest tests/integration --collect-only -q` | Passed collection; 39 tests collected. This is not execution of database tests. |
| `make test-integration` | Blocked: `permission denied while trying to connect to the docker API at unix:///Users/apple/.docker/run/docker.sock`. No container or migration was started by this command. |
| `git diff --check` | Passed. |

Unit tests use an explicitly isolated SQLite adapter for service/API validation, retry handling, ownership, pagination, and request/history rollback. Its test-only `create_all` and JSON type adapter do not replace production Alembic or establish PostgreSQL trigger behavior. PostgreSQL integration coverage uses shared disposable migrated databases and includes creation/read/retry, invalid references, role/department constraints, missing-history rejection, state/version history guards, preserved fixtures across downgrade/upgrade, and the existing tenant/seed/model-drift suite. These PostgreSQL checks remain unverified here.

Before accepting the milestone, run `make dev` and `make test-integration` in an environment with Docker access, or the base-only equivalents using `COMPOSE_FILES="-f infra/compose.yaml"`. Fresh migration execution, live constraint enforcement, seed compatibility, and migration cycles must pass. No Phase 1 milestone 2 work is authorized by this document.

## Changed files

Modified:

```text
AGENTS.md
README.md
apps/api/app/db/models.py
apps/api/app/domain/types.py
apps/api/app/main.py
packages/contracts/openapi.json
packages/contracts/src/api.d.ts
tests/contracts.test.mjs
tests/integration/test_database.py
tests/unit/test_foundation.py
```

Added:

```text
apps/api/app/api/__init__.py
apps/api/app/api/dependencies.py
apps/api/app/api/requests.py
apps/api/app/domain/errors.py
apps/api/app/domain/identity.py
apps/api/app/schemas/__init__.py
apps/api/app/schemas/core.py
apps/api/app/services/__init__.py
apps/api/app/services/requests.py
apps/api/migrations/versions/0002_request_foundation.py
docs/PHASE_1_MILESTONE_1.md
tests/integration/conftest.py
tests/integration/test_request_persistence.py
tests/unit/test_requests.py
```

All changes remain unstaged. No dependency lock, Compose, worker, frontend source, or deployment configuration change is retained.
