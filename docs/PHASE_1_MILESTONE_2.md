# Phase 1 milestone 2: trusted authentication

Status: complete, live auth integration verified, committed and pushed, CI green, as confirmed by the project owner before milestone 3. The implementation-pass limitations below are historical; they are not outstanding milestone 2 blockers. No authentication architecture change is authorized in milestone 3.

## Implemented architecture

- PostgreSQL `auth_sessions` stores only SHA-256 session digests, tenant/user references and UTC lifecycle timestamps. Cookies contain 256-bit random opaque tokens. No JWT/refresh tokens, external identity providers or Redis session store.
- The existing `Principal(organization_id, user_id)` interface is unchanged. Auth uses a separate short transaction; request services retain tenant/requester predicates and current-role authorization. Creation no longer accepts client `requester_id`.
- Session checks enforce existence, revocation, idle/absolute expiry, active user and matching configured organization. Absolute expiry is never extended. Persisted activity is touched only when older than five minutes, with conditional validity checks to prevent revival. The 30-minute idle deadline is measured from the last persisted activity; throttling can conservatively expire up to five minutes before the last unpersisted activity.
- Login replaces only the session identified by the current cookie. Logout affects only that device. Database account-disable triggers revoke all sessions, including across later reactivation. Explicit password changes use `replace_password` in the caller's transaction to revoke all devices; ordinary same-password rehash on login preserves other devices. There is no password-change/reset HTTP endpoint.
- Argon2id uses approved `argon2-cffi`, with centrally configured initial 64 MiB/three iterations/parallelism four. Unknown/passwordless users verify a startup-warmed dummy hash. Passwords and raw session tokens are not logged. Missing approved dependencies fail startup; there is no production password fallback.
- HTTPS cookies use `__Host-`, Secure, HttpOnly, SameSite=Lax, Path=/ and no Domain. Explicit loopback HTTP uses a different non-Secure name. Authenticated mutations require allowed Origin and constant-time verification of a session-bound HMAC CSRF token. Safe methods do not require CSRF. Login additionally requires JSON. Credentialed CORS uses exact origins; auth responses use `Cache-Control: no-store`.
- Login-only Redis counters use atomic Lua, configurable IP/account limits and opaque HMAC identifiers. No forwarded address headers are trusted; Compose disables Uvicorn proxy interpretation. Redis failure returns sanitized login 503. Existing authenticated application requests do not call Redis.
- API-only configuration validates a random 32-byte hex secret, organization, exact origins and timeout ordering at startup. OpenAPI export does not execute startup or connect to services. Setup/CI generate an ignored local secret without printing or overwriting existing values. No shared/default account passwords or automatic seed activation.

## API and migrations

`POST /auth/login` accepts email/password and sets the session cookie; `GET /auth/me` returns current user/roles, absolute expiry and CSRF token; `POST /auth/logout` revokes the current session and clears the cookie. Invalid credentials/account states share generic 401. Auth absence/expiry/revocation is 401; origin/CSRF is 403; non-JSON login is 415; invalid input is 422; login limits are 429 with Retry-After; backend unavailability is sanitized 503. Logout is idempotent after the session becomes unavailable, while preserving Origin verification.

Migration `0003_auth_sessions` adds sessions, indexes, disablement revocation and organization-scoped canonical email uniqueness. The explicit rule is ASCII email identifiers, trimming outer ASCII spaces and lowercasing the entire address. PostgreSQL uniqueness uses `lower(btrim(email))`; migration preflight fails on existing collisions rather than rewriting accounts. No additional user columns are needed. Deterministic seeds remain unchanged.

The interactive `app.core.init_account` command selects an existing account by email in the configured organization, refuses already initialized credentials, and accepts password input through getpass. It requires local environment, local database host and a terminal. Its benchmark mode measures configured Argon2 without printing a password.

## Actual verification

Registry access failed. Executed `UV_CACHE_DIR=.cache/uv uv add 'argon2-cffi>=25.1,<26'`: PyPI metadata fetch failed with DNS lookup failure. The offline equivalent failed because Alembic metadata was not cached. `uv add --frozen` then declared the approved dependency without inventing a lock. **The tracked `uv.lock` has not been regenerated and does not yet include Argon2.** Normal frozen uv execution also attempted rebuilding the project and failed retrieving Hatchling metadata. Checks below therefore use existing installed tools explicitly with `--no-sync`; this is not locked dependency installation verification.

| Exact command | Actual result |
| --- | --- |
| `python3 scripts/init_auth_config.py` | Passed; configured ignored local `.env` without printing secrets. |
| `UV_CACHE_DIR=.cache/uv uv run --frozen --no-sync pytest tests/unit -q` | 53 passed; 2 real Argon2 tests BLOCKED/skipped; one upstream Starlette/httpx deprecation warning. |
| `UV_CACHE_DIR=.cache/uv uv run --frozen --no-sync ruff check apps tests scripts` | Passed. |
| `UV_CACHE_DIR=.cache/uv uv run --frozen --no-sync ruff format --check apps tests scripts` | Passed; 56 files. |
| `UV_CACHE_DIR=.cache/uv uv run --frozen --no-sync mypy` | Passed; 56 source files. |
| `CONTRACT_PYTHON=.venv/bin/python make contracts` | Passed; actual FastAPI OpenAPI and approved TypeScript generator. |
| `CONTRACT_PYTHON=.venv/bin/python make contracts-check` | Passed; no drift. |
| `CONTRACT_PYTHON=.venv/bin/python node --test tests/contracts.test.mjs` | Passed; 7 tests, zero skipped, including negative drift/tampering. |
| `npm run typecheck` | Passed; contracts, web and check configuration. Incidental Next-generated `next-env.d.ts` changes were restored; no frontend UI/source change retained. |
| `UV_CACHE_DIR=.cache/uv uv run --frozen --no-sync pytest tests/unit/test_compose.py -q` | Passed; 4 configuration regression tests, including API-only secret scope and disabled proxy-header parsing. |
| `make compose-check` | Passed; both base and local configurations. Health checks remain unchanged; web remains non-root. |
| `UV_CACHE_DIR=.cache/uv uv run --frozen --no-sync alembic upgrade head --sql > /tmp/actiondesk-milestone2-migrations.sql` | Passed offline generation only; no migration executed against PostgreSQL. |
| `UV_CACHE_DIR=.cache/uv uv run --frozen --no-sync pytest tests/integration --collect-only -q` | 46 tests collected; no execution implied. |
| `UV_CACHE_DIR=.cache/uv uv run --frozen --no-sync pytest tests/integration -q --maxfail=1 > /tmp/actiondesk-milestone2-integration.log 2>&1` | Blocked at first database fixture: localhost:5432 connection failed with `Operation not permitted`. No integration tests passed. |
| `make test-integration` | Blocked: Docker socket `unix:///Users/apple/.docker/run/docker.sock` permission denied. |
| `git diff --check` | Passed; no whitespace errors. |

API unit tests explicitly substitute a password adapter and startup warmup; these verify HTTP/session behavior, not Argon2 cryptography or PostgreSQL triggers. Runtime never imports these adapters. The two real password tests are not counted as passed; on GitHub Actions missing Argon2 fails rather than skips them. PostgreSQL integration tests retain real identity resolution and add live login/request/logout, disable/reactivate, credential revocation, same-password rehash/device preservation, tenant/session/email constraints, collision migration and real Redis throttling. Existing migration/seed/domain tests remain included.

## Host verification required

From a normal terminal with package-registry access and Docker Desktop running:

```sh
uv lock
uv sync --locked
make setup
make verify
```

For CI-equivalent runtime selection, use `make verify COMPOSE_FILES="-f infra/compose.yaml"`. Review the real regenerated `uv.lock`. All real password tests, session/migration/seed integration tests and stack health must pass before accepting milestone 2. Actual Argon2 benchmarking and interactive account initialization were not executed in the sandbox. No hosted CI rerun is claimed.

No OAuth, SSO, MFA, reset/verification/invite flow, frontend auth UI, approval, AI, notification or deployment feature is introduced. No worker/Celery behavior is changed.

## Changed files

Modified:

```text
.env.example
.github/workflows/ci.yml
AGENTS.md
Makefile
README.md
apps/api/app/api/dependencies.py
apps/api/app/db/models.py
apps/api/app/domain/errors.py
apps/api/app/main.py
apps/api/app/schemas/core.py
apps/api/app/services/requests.py
docs/PHASE_1_MILESTONE_1.md
infra/compose.yaml
packages/contracts/openapi.json
packages/contracts/src/api.d.ts
pyproject.toml
tests/contracts.test.mjs
tests/integration/test_database.py
tests/integration/test_request_persistence.py
tests/unit/test_compose.py
tests/unit/test_foundation.py
tests/unit/test_requests.py
```

Added:

```text
apps/api/app/api/auth.py
apps/api/app/api/cors.py
apps/api/app/core/auth_config.py
apps/api/app/core/init_account.py
apps/api/app/domain/email.py
apps/api/app/schemas/auth.py
apps/api/app/services/auth.py
apps/api/app/services/login_limits.py
apps/api/app/services/passwords.py
apps/api/migrations/versions/0003_auth_sessions.py
docs/PHASE_1_MILESTONE_2.md
docs/adr/0002-authentication.md
scripts/init_auth_config.py
tests/__init__.py
tests/conftest.py
tests/integration/__init__.py
tests/integration/test_auth_persistence.py
tests/unit/__init__.py
tests/unit/conftest.py
tests/unit/support.py
tests/unit/test_auth.py
tests/unit/test_password_hashing.py
```

All changes remain unstaged; nothing was committed or pushed. The generated local `.env` is ignored. `uv.lock` is unchanged pending real resolution; no fabricated lock, frontend source or worker change is retained.
