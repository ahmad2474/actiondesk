# Phase 0 dedicated verification and remediation pass

14 October 2026. **Phase 0 remains incomplete.** This report supersedes the prior implementation-pass results. Provisional source acceptance does not satisfy the runtime exit gate. Phase 1 was not started.

## 1. Environment actually inspected

| Item | Executed command | Observed result |
| --- | --- | --- |
| OS/architecture | `uname -srm`; `sw_vers` | macOS 15.8.1, build 24H32; Darwin 24.6.0, x86_64 |
| Docker | `docker version` | CLI 29.8.0, darwin/amd64, desktop-linux context; Engine version/availability **unverified** because socket access is denied |
| Compose | `docker compose version` | v5.5.1; daemon-free configuration validation works |
| Default Python | `python3 --version` | 3.14.7 |
| Supported project Python | `/Users/apple/.local/bin/python3.12 --version`; `.venv-checks/bin/python --version` | Both 3.12.14; project remains Python 3.12 |
| uv | `uv --version` | 0.12.13 |
| Node/npm | `node --version`; `npm --version` | Node v26.4.0; npm 11.17.0; planned Docker/CI Node line remains 22 |
| Git | `git --version`; `git status --short` | Git 2.39.5 (Apple Git-154); no repository exists |
| PyPI access | `curl -I --connect-timeout 5 --max-time 10 https://pypi.org/simple/` | Failed, curl 6: `Could not resolve host: pypi.org` |
| npm access | Same curl flags for `https://registry.npmjs.org/` | Failed, curl 6: `Could not resolve host: registry.npmjs.org` |

Package registry access from the local execution environment is blocked by DNS failure. Reading public documentation through the browsing tool does not establish that package downloads work.

Exact Docker blocker:

```text
permission denied while trying to connect to the docker API at
unix:///Users/apple/.docker/run/docker.sock
```

## 2. Dependency restoration and version control

| Executed command | Result |
| --- | --- |
| `UV_CACHE_DIR=.cache/uv uv sync --python /Users/apple/.local/bin/python3.12` | Failed fetching Pydantic metadata from PyPI: DNS lookup failure |
| `UV_CACHE_DIR=.cache/uv uv lock --offline --find-links .cache/wheelhouse` | Failed: Alembic is not cached; full dependency graph cannot resolve offline |
| `make setup` | Stopped at `uv sync`, fetching PyYAML metadata failed on DNS; later setup stages did not run |
| `UV_CACHE_DIR=.cache/uv uv lock` | Failed on PyPI DNS; **no uv.lock was generated** |
| `npm ci --offline --cache .cache/npm --ignore-scripts --no-audit --no-fund` | Installed 350 previously locked frontend/tool packages before the generator manifest change; this does not prove the new intended dependency set installs |
| `npm install --save-dev openapi-typescript@7 --cache .cache/npm --fetch-retries=0 --fetch-timeout=10000 --no-audit --no-fund` | Failed: npm `ENOTFOUND`, `getaddrinfo ENOTFOUND registry.npmjs.org` |
| `npm install --cache .cache/npm --fetch-retries=0 --fetch-timeout=10000 --no-audit --no-fund` | Also failed after declaring the intended generator; npm lock reconciliation remains pending |
| Manifest-vs-lock comparison using Node | Reported `npm lock reconciliation pending: openapi-typescript` |
| `git init -b main` | Failed: `.git: Operation not permitted` |
| `git status --short`; `git remote -v` | Both failed: not a Git repository |

The intended `openapi-typescript` dependency and its Node API are now declared/wired. The temporary conversion implementation was removed. Missing packages cause generation to fail; no fallback is used. Existing TypeScript declarations are legacy output and have **not** been regenerated with the intended package.

`make setup` now resolves manifest changes with uv/npm, then installs Chromium. CI and Docker remain strict (`uv sync --frozen`, `npm ci`). Setup must reconcile and retain both lockfiles once downloads work. No supported lock format was manually fabricated, and no lockfile or other source was committed because Git initialization is denied. No remote or push was performed.

`.gitignore` and `.dockerignore` were strengthened for credential directories/files, key/certificate files, local volume directories and backups, in addition to `.env`, caches, virtual environments, node_modules and build artifacts. Source migrations and synthetic seed data remain includable. Git-based ignore matching is not claimed verified while repository initialization is blocked.

## 3. Quality checks actually run

Python checks used the existing isolated `.venv-checks` containing cached tools/partial dependencies, not a complete locked uv project environment.

| Executed command | Actual outcome |
| --- | --- |
| `PYTHONPATH=apps/api:apps/worker .venv-checks/bin/python -m pytest tests/unit -q` | **18 passed**, 2 upstream Starlette/AnyIO deprecation warnings |
| `.venv-checks/bin/ruff check apps tests scripts --output-format concise` | Passed after remediation |
| `.venv-checks/bin/ruff format --check apps tests scripts` | Passed; 23 Python files |
| `PYTHONPATH=apps/api:apps/worker .venv-checks/bin/mypy --show-error-codes` | Failed: 19 errors across 7 files from unavailable SQLAlchemy/Redis/Alembic modules and dependent types; full mypy is **not passed** |
| `PYTHONPATH=apps/api:apps/worker .venv-checks/bin/python -m pytest tests/integration -q` | Failed during collection: `ModuleNotFoundError: No module named 'alembic'`; no PostgreSQL tests executed |
| `node --test tests/contracts.test.mjs` | **4 comparator tests passed; 3 real-generator tests skipped as BLOCKED**, not counted as passing |
| `npm run lint` | ESLint passed for web, generator, browser configuration/tests |
| `npm run typecheck` | Passed for existing declarations, web/Next route types and Playwright configuration/tests; does not verify intended generator output |
| `NEXT_TELEMETRY_DISABLED=1 npm run build` | Next.js 16.3.5 production build passed |
| `make compose-check` | Compose configuration parsed successfully without accessing the daemon |
| Python source syntax compilation | All current sources compiled without importing missing dependencies |
| `make verify` | Stops at first frozen uv command: missing `uv.lock`; complete local CI-equivalent sequence is **not passed** |

CI YAML and run-step shell syntax are covered by a passing unit test. Hosted CI was not executed; no remote is authorized. npm emitted a deprecation warning that cached ESLint 9.39.5 is outside its support window; compatible toolchain maintenance remains a follow-up before final dependency acceptance.

## 4. Contracts and negative drift verification

Executed:

```sh
PYTHONPATH=apps/api .venv-checks/bin/python scripts/export_openapi.py --stdout > /tmp/actiondesk-verification-openapi.json
PYTHONPATH=apps/api CONTRACT_PYTHON=.venv-checks/bin/python npm run contracts
PYTHONPATH=apps/api CONTRACT_PYTHON=.venv-checks/bin/python npm run contracts:check
```

The actual FastAPI export succeeded and matched stored OpenAPI JSON, with only `/health` and `/ready`. Both intended TypeScript generation and its full drift command failed:

```text
Cannot find package 'openapi-typescript' imported from .../scripts/contracts.mjs
```

Comparator unit tests deliberately changed the JSON file, changed the declaration file, and removed a file. All detected drift without rewriting it. These are tests of comparison logic, **not** a claim of end-to-end contract verification.

Three blocked tests require the real package: reproducible generation from actual FastAPI export; an exported API field change causing JSON and TS drift; CLI returning nonzero after tampering. They must run before completion, followed by regeneration of the tracked declarations and `make contracts-check`.

## 5. Stack, health, browser and lifecycle attempts

Executed `make dev`, Compose `ps`, `make worker-smoke`, `make down`, Compose `restart --timeout 30`, and `make test-integration`. Every Docker operation failed with the socket denial above. No container was started, inspected as healthy, stopped, restarted, or verified as running by this pass.

Executed curl requests with 3-second connection / 5-second total timeout to:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/ready`
- `http://127.0.0.1:3000/`

All failed with curl 7, unable to connect. No live endpoint or frontend load passed. In-process unit health/readiness tests do pass, but do not establish PostgreSQL/Redis connectivity or container health.

Standalone Next startup was attempted from `apps/web`:

```sh
NEXT_TELEMETRY_DISABLED=1 ../../node_modules/.bin/next start --hostname 127.0.0.1 --port 3000
```

It failed with `listen EPERM: operation not permitted 127.0.0.1:3000`.

`npm run test:web -- --reporter=line` ran the available desktop/mobile test definitions. **Both failed before page execution** because Chromium launch was denied by macOS sandbox IPC:

```text
bootstrap_check_in org.chromium.Chromium.MachPortRendezvousServer...:
Permission denied (1100)
process did exit ... signal=SIGTRAP
```

Graceful shutdown/restart, runtime worker success, healthy PostgreSQL/Redis, and browser behavior remain **blocked**, not passed.

## 6. Database and tenant verification remediation

The integration suite now uses a new disposable database for each test, with unique `actiondesk_test_...` names; teardown drops only that generated database. Added/expanded checks cover:

- Empty database migration to head, repeated upgrade and `alembic check`.
- Explicit table/column/FK/unique/index inspection against models.
- Independent 10-record minimal seed twice in a fresh database.
- Additive 10-to-100 seed and repeated 100-record seed snapshots, including fixed role-grant timestamps.
- Downgrade to base / enum and function cleanup / upgrade / reseed snapshot equivalence in a disposable database only.
- Request event update and delete rejection, role-qualified managers, self-approval rejection and finance processing attribution.
- Sixteen organization-qualified relationship violations across users, roles, managers, requests, policies, fields, actors, approvals and outbox; errors must be SQLSTATE `23503`.

These checks are written but **unexecuted** because database test collection and Docker access fail. No downgrade or seed command was executed against any database. Schema/model comparison and database idempotence cannot be declared verified.

[Tenant-integrity review](TENANT_INTEGRITY.md) maps the source constraints and makes future query/object authorization boundaries explicit. No business authorization feature was implemented. Database integrity does not replace object visibility checks, active role checks, or organization-scoped queries.

## 7. Fixes made and remaining exit work

Fixes made in this pass:

1. Removed the temporary generator; declared/wired `openapi-typescript`; added comparison-negative and real-generation tests. Installation and updated artifacts remain pending.
2. Fixed the no-op probe to drain Kombu's actual subscribed consumer connection, wait for task-event activation acknowledgment and restore Phase 0's default event mode. Three simulated regression tests passed; live Celery is unverified. [Kombu source reference](https://docs.celeryq.dev/projects/kombu/en/stable/_modules/kombu/mixins.html).
3. Made seed role insertion ordering deterministic, improved database test isolation/savepoint rollback, added independent minimal-seed and safe downgrade/upgrade checks, and expanded tenant/schema inspection coverage.
4. Added explicit first-party Ruff import configuration and a test import path for verification helpers. All lint/format checks passed afterward.
5. Strengthened secret/volume ignore rules and updated README, ADR, plan, AGENTS.md and this report to match the current state.

Required to finish, in an environment permitting registry downloads, `.git` writes, Docker socket access, localhost binding and Chromium IPC:

1. Install the intended package and complete uv project dependencies; generate real `uv.lock`, reconcile npm lock, review both and commit locally. No remote/push.
2. Regenerate TS using `openapi-typescript`; run the three blocked real-generator tests and full drift check, including the negative case.
3. Run the documented stack setup/start process; verify all five services, health/readiness, frontend and no-op task execution.
4. Run actual fresh migrations, database inspection, both independent seed paths/idempotence, tenant FK tests and disposable downgrade/upgrade.
5. Complete full mypy, integration and browser checks; confirm graceful stop/start and preserved data. Record actual exit codes and health results.
6. Update this report only with observed evidence. Phase 0 may then be considered for completion; **stop for explicit approval before Phase 1**.

No Phase 1 feature, external AI integration, AWS deployment, paid service, real customer data or remote Git operation was introduced.
