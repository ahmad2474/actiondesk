# ActionDesk

AI-assisted internal operations platform. Phase 0 provides the skeleton and local infrastructure. Phase 1 milestones 1 and 2 provide tenant-aware creation/reads and PostgreSQL opaque-cookie authentication. **Milestone 3** adds deterministic manual service, expense and leave transitions, durable approval evidence, participant visibility and scoped work queues. AI, notifications and frontend workflow UI remain deferred.

**Current status:** Phase 0 and milestones 1 and 2 are owner-confirmed complete with live verification and green CI. Milestone 3 implementation and current validation results are in [the milestone report](docs/PHASE_1_MILESTONE_3.md). This work is uncommitted. Milestone 4 requires explicit approval.

## Specification and decisions

[PRD v1.1](docs/ActionDesk_PRD_Technical_Architecture_v1_1.pdf) is authoritative; [v1](docs/ActionDesk_PRD_Technical_Architecture_v1.pdf) is background. [AGENTS.md](AGENTS.md), [Phase 0 plan](docs/PHASE_0_PLAN.md), and [foundation ADR](docs/adr/0001-foundation.md) describe engineering constraints and approved decisions. Phase 1 authorization stops at milestone 3; [the approved design](docs/PHASE_1_MILESTONE_3_DESIGN.md) records its policy decisions.

## Local setup

Run commands from the repository root. Prerequisites: Docker Engine/Desktop with Compose v2+ and a running daemon; Node.js 22+; npm; uv; Make; Git. uv manages Python 3.12. First downloads/image builds may take longer than ten minutes.

```sh
cp .env.example .env
make setup
make dev
```

`make setup` initializes missing auth settings in ignored `.env`, then runs `uv sync`, `npm install`, and Chromium installation. Existing secrets are preserved; no passwords are generated or seeded. The repository includes `uv.lock` and `package-lock.json`. Setup can update these lockfiles when manifests change; review any resulting diff. CI and Docker builds use frozen/clean installs (`uv sync --frozen`, `npm ci`).

After setup, **`make dev` is the one command to start the complete local stack**. It builds images, starts PostgreSQL and Redis, runs Alembic and the 100-request seed, then starts API, worker, and web. It waits for health checks; bootstrap failures block dependent services. The local development startup and CI-equivalent base startup have both passed verification.

`infra/compose.yaml` is the base configuration and has no host source mounts. Local Make targets add `infra/compose.local.yaml`, retaining source bind mounts/hot reload and the local Next.js cache volume. CI runs `make verify COMPOSE_FILES="-f infra/compose.yaml"`; recursive Make targets inherit that selection. The web image keeps `USER node` and its image-owned writable source directory, so CI never replaces it with a checkout owned by a different host UID. No root runtime or workspace permission changes are needed. Failure diagnostics and all health probes remain enabled.

- Web: http://127.0.0.1:3000
- API liveness: http://127.0.0.1:8000/health
- API readiness: http://127.0.0.1:8000/ready
- OpenAPI: http://127.0.0.1:8000/openapi.json and `/docs`

The example database password is for local synthetic development only. PostgreSQL and Redis have no host-published ports. API/web bind to localhost. Do not deploy this Compose file or share its credentials externally. Seed users remain inactive and passwordless until explicitly initialized. Normal bootstrap never activates accounts.

## Architecture

```mermaid
flowchart LR
    Browser --> Web[Next.js / TypeScript]
    Browser --> API[FastAPI health and request API]
    API --> DB[(PostgreSQL)]
    API --> Redis[(Redis)]
    Bootstrap[Migration + synthetic seed] --> DB
    Worker[Celery no-op worker] --> Redis
```

Web/API/worker are separate processes in one monorepo. API and worker share the Python package defined in root `pyproject.toml`. PostgreSQL owns workflow state, approvals, policies, history, and outbox records. Redis/Celery is transport; no durable business jobs, relay, AI calls, or notifications run in Phase 0.

`apps/api/app/domain` holds types and approved safety predicates; `db` contains SQLAlchemy models and fixture persistence. Request routers, typed schemas, and transaction services live in `api`, `schemas`, and `services`. Alembic revisions live in `apps/api/migrations`; milestone 1 adds `0002_request_foundation` without rewriting the original foundation migration. `packages/contracts` contains FastAPI OpenAPI and generated TS declarations. `data/seed/requests.json` is canonical synthetic input. Tests cover unit, PostgreSQL integration, and browser smoke checks.

## Schema and fixtures

The schema includes organizations, departments, users, a fixed role catalog, role assignments, employee managers, department managers, versioned approval policies, requests, typed fixture fields stored as JSONB, immutable request events, approvals, and an initial outbox table. Milestone 1 requires a department on each request and a matching history event for creation or status/version changes at transaction commit.

Roles are employee, manager, finance, and admin, with multiple assignments per user. Manager relationships reference manager-role assignments. Composite organization foreign keys prevent cross-organization references. Approval steps preserve legacy nominees and use immutable candidate snapshots and actual-actor decisions for new submissions. Versioned policies require manager approval for all expenses, plus finance above an explicitly configured threshold. Expense approval and finance processing are distinct actions; no money moves. Conservative cancellation/withdrawal is supported before final approval/work starts. Reversal/reopening and correction/resubmission are deferred. See [tenant-integrity review](docs/TENANT_INTEGRITY.md) for the relationship map and [milestone 1 notes](docs/PHASE_1_MILESTONE_1.md) for the request API boundary.

Request endpoints are `POST /requests`, `GET /requests/{request_id}`, and `GET /requests`. They require a valid session cookie. Client-supplied identity headers never grant access; `requester_id` is no longer accepted in creation input. Creation derives requester and organization from the trusted session and requires a UUID `Idempotency-Key`, allowed `Origin`, and `X-CSRF-Token`. Service requests start at `SUBMITTED`; expense/leave requests start at `DRAFT`. Get/list are restricted to the requester's own organization and records. There are no update or transition endpoints.

```sh
make migrate
make seed          # Default: 100 requests
make seed-smoke    # Additive 10-request subset; never reduces existing data
```

Seeds use stable UUIDs, fixed UTC timestamps, fictional `.invalid` addresses, and Decimal amounts serialized as strings. They run in one transaction under an advisory lock. Repeated commands preserve existing rows; they never reset requests or rewrite events. Fixture IDs and policy versions are immutable: intentional fixture changes should use new IDs/versions, not overwrite existing business history. Seed commands do not dispatch outbox jobs. No attachments or real customer data are present.

## Verification

```sh
make lint
make typecheck
make test
make contracts-check
make compose-check
make dev
make test-integration
make worker-smoke
make test-web
npm run build
```

`make verify` runs these checks as one sequence using the base + local override. To reproduce CI without host source mounts, select the base configuration explicitly:

```sh
make verify COMPOSE_FILES="-f infra/compose.yaml"
```

Both verification commands leave their stack running. Use `make down` for the local configuration or `make down COMPOSE_FILES="-f infra/compose.yaml"` for the base-only configuration. Integration checks create/migrate a temporary PostgreSQL database and drop only that generated database. Each database test uses its own fresh disposable database. Tests verify independent 10/100-record seed paths, repeat snapshots, safe downgrade/upgrade, deployed tables/FKs/uniques/indexes, 16 cross-organization references, role separation, append-only events, model/migration drift, and live PostgreSQL/Redis readiness. They require the local database role's ability to create test databases; do not run with production connection strings.

Browser smoke tests verify the served placeholder on desktop/mobile. Worker smoke checks ping and observes a no-op task success event; it does not claim durable job recovery. The CI workflow runs the same checks on Linux without AI keys. The project owner confirmed that GitHub Actions passed after the Compose mount split.

`/health` indicates process liveness independent of dependencies. `/ready` is 200 only when PostgreSQL responds, the database revision is the expected Alembic head, and Redis responds; otherwise it returns 503 with sanitized component statuses. It does not verify worker liveness; Compose has a separate worker probe. Each API response includes a validated/generated `X-Request-ID`. No request bodies, credentials, or dependency exception text are returned by health checks.

## API contracts

```sh
make contracts       # Export OpenAPI and regenerate TypeScript
make contracts-check # Compare without changing generated files
```

The generation command imports FastAPI without connecting to PostgreSQL/Redis. Source schemas remain Pydantic/OpenAPI; frontend types are generated, not separately hand-maintained.

The temporary converter has been removed. `scripts/contracts.mjs` now calls the approved `openapi-typescript` Node API. Generation and drift checks fail if that dependency is missing; there is no fallback. TypeScript contracts are generated from the actual FastAPI OpenAPI schema. Generation and drift checks are included in the passing foundation workflow.

Comparator tests deliberately change or remove artifact files to verify detection without overwriting them. Real-generator tests additionally mutate an exported FastAPI schema and test CLI exit status; these are skipped when `openapi-typescript` is absent. Install the approved dependencies before verification; a missing generator also makes `make contracts-check` fail.

## Troubleshooting

- Docker socket denied or daemon unavailable: start Docker Desktop and run in an environment allowed to access its socket. `make compose-check` validates configuration without a daemon but does not prove startup.
- DNS/registry errors: setup needs access to PyPI, npm, and container registries. Resolve connectivity, then rerun `make setup`.
- Missing `uv.lock`: restore the tracked lockfile from Git. Backend Docker builds and CI intentionally require it; intentional dependency changes require regenerating and reviewing the lock.
- Port binding denied: local execution needs permission to listen on localhost. Choose available `WEB_PORT`/`API_PORT` in `.env`; for browser tests set `WEB_BASE_URL` accordingly.
- Bootstrap exits: inspect `make logs` for migration/seed failure. Do not bypass migration ordering or use `create_all`.
- Readiness 503: inspect component statuses and Compose service health; rerun `make migrate` for a revision mismatch after reviewing migrations. Do not edit `alembic_version` manually.
- Changed PostgreSQL password with an existing volume: initialization variables only apply to a new database. Restore the local value or intentionally manage the existing database credentials.
- Missing `openapi-typescript` or npm lock mismatch: restore registry access and rerun `make setup`; review the updated npm lock, regenerate with `make contracts`, then run `make contracts-check`.
- Contract drift: regenerate with the installed intended package, review the schema/type diff, and rerun the checks.
- User cannot log in: initialize an explicitly selected existing local account as documented below. Seeds remain inactive/passwordless; normal bootstrap does not enable login. Invalid credentials, inactive users and unknown users return the same 401. Missing/expired/revoked cookies also return 401; CSRF/origin errors return 403.
- `make down` stops containers and preserves data. `docker compose --env-file .env -f infra/compose.yaml -f infra/compose.local.yaml down --volumes` deletes local data and the local Next.js cache and is an explicit destructive reset, never part of normal startup.

No AWS deployment, external AI integration, real-user onboarding, or paid services are part of this foundation.

## Local authentication

After starting the stack, initialize a chosen existing synthetic account interactively:

```sh
docker compose --env-file .env -f infra/compose.yaml -f infra/compose.local.yaml exec api uv run --no-sync python -m app.core.init_account --email '<existing-account-email>'
```

The command prompts privately for a new password and confirmation. It requires a local terminal/database, refuses unknown or already initialized accounts, and never changes normal seed/bootstrap behavior. For a base-only stack, omit the local override. Run the same module with `--benchmark` instead of `--email` to measure the configured Argon2 profile without printing credentials.

`POST /auth/login` accepts JSON email/password and requires an exact allowed `Origin`. It sets an HttpOnly session cookie and returns a credential-free user, current roles, absolute expiry and session-bound CSRF token. `GET /auth/me` returns the same information without CSRF requirements. `POST /auth/logout` requires Origin/CSRF for a valid session and revokes only that session. Auth responses are not cached. There is no refresh endpoint or auth UI.

Cookies use `__Host-actiondesk_session` with Secure/HttpOnly/SameSite=Lax/Path=/ and no Domain under HTTPS. Explicit loopback HTTP development uses `actiondesk_session_local` without Secure. `ACTIONDESK_AUTH_ALLOWED_ORIGINS` is an exact JSON origin list; update it when changing local ports. No wildcard credentialed CORS or trusted identity headers are supported. Uvicorn proxy-header interpretation is disabled in this Compose configuration.

Sessions expire after 30 minutes from the last persisted activity and at an immutable eight-hour absolute deadline. Touch writes happen only after five minutes: idle expiry is conservative and may occur up to five minutes earlier than the last unpersisted activity. An expired session is never revived by touching it. Login replaces only a session represented by the current cookie; other devices remain active. Disabling an account revokes all its sessions; explicit credential replacement must use the transactional password service. Rehashing the same password on login preserves other devices.

Argon2 profile settings are `ACTIONDESK_AUTH_ARGON_MEMORY_KIB`, `ACTIONDESK_AUTH_ARGON_TIME_COST` and `ACTIONDESK_AUTH_ARGON_PARALLELISM` (initial defaults 65536/3/4). Auth secret, origin and session settings are API-only; the worker needs no auth secret. Redis limits login attempts only (initial defaults 20/IP/minute and 10/account/15 minutes). Redis failure returns sanitized 503 for login and does not affect existing session authentication.

## Manual workflow API

`POST /requests/{request_id}/transitions` requires the existing session, allowed Origin, CSRF token and a UUID `Idempotency-Key`. Its discriminated body includes `action`, `expected_version` and a nonempty `reason`. `submit` additionally requires typed `data` with `type: expense` or `type: leave`; other actions have specific fields (`assignee_id`, `resolution`, `approval_id` or `reference`). See OpenAPI for the exact schemas. Monetary values are JSON strings with at most two fractional digits; current supported currency is PKR. There is no arbitrary status PATCH.

New service requests begin SUBMITTED and progress through triage, assignment, start, resolution and closure. Expense/leave drafts submit and route atomically into manager review with two version increments/events. Leave approval is terminal. Expense processing requires all required decisions and a finance actor distinct from the requester. No external payment is performed.

`GET /requests` defaults to owned records. `scope=participant`, `assigned`, `triage` and `processing` expose only authorized work. `GET /approvals` paginates currently actionable snapshotted steps; future steps and ineligible candidates are excluded. Expense/leave content has no blanket admin visibility.

Submission requires an explicitly selected immutable policy in `active_approval_policies`. Seeds preserve historical example definitions and do not activate them. Configure a reviewed policy version and threshold as documented in [the milestone report](docs/PHASE_1_MILESTONE_3.md); missing policy/candidates safely return 409. Do not reuse seed example amounts as universal rules.

Historical seeds remain readable to their owners and unvalidated for live approval mutations. Explicit read-only assessment:

```sh
docker compose --env-file .env -f infra/compose.yaml -f infra/compose.local.yaml exec -T api uv run --no-sync python -m app.core.validate_legacy_approvals --organization-id '<organization UUID>'
```

The report emits only request IDs and evidence blockers, returns 1 when blocked, and changes no data. It does not invent snapshots or decisions. Activating historical plans requires a separately reviewed migration/repair procedure.
