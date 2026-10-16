# Milestone 6B Phase 2: frontend read integration

Owner authorization follows committed/pushed, CI-green 6B Phase 1 and the browser
stability fix. PRD v1.1 Sections 16.1, 16.5 and 16.6–16.7 govern consistency,
disclosure and UI sequencing. This is frontend read integration within Phase 1 of
the overall PRD, not PRD Phase 2 durable execution. No workflow mutations, changed
authorization, new dependencies, migrations or external effects are introduced.

## Architecture and screens

- Both server reads and the same-origin adapter use the fixed upstream and shared
  read allowlist/query builder. It admits capabilities, creation options and only
  approvals/reversals/service_work/finance_processing queues. Owned lists force
  `scope=mine`; only limit/offset are forwarded. No directory or policy endpoint.
  Authentication POSTs alone remain admitted; workflow/create POSTs remain blocked.
- Existing server components compose generated contract aliases; no independent
  transport models, global browser store, optimistic state or data framework.
- Detail is participant-visible according to the backend, replacing the old
  owner-only frontend restriction. Organization/request identity is checked before
  rendering. Capabilities supply action labels, participant names, department,
  timezone and expressly authorized paged assignee choices. Unknown names retain
  neutral identifier labels. Current candidate lists are not rendered as a directory.
- My Requests keeps its owned pagination and adds version-matched capabilities and
  department names. At most 20 items are enriched concurrently; the bounded N+1
  reads favor reuse of existing scoped APIs over a new backend list contract.
- Approvals contains independently loaded approval and reversal queues. Service
  Work and Finance Processing use their dedicated queues. Pagination uses backend
  `has_more`, preserves independent approval/reversal offsets and never estimates
  hidden totals. Finance holds use backend blockers; decimal strings stay strings.
- New request loads only authorized types and paged departments into disabled
  choice controls. There is no intake submission or draft creation in this phase.
- Shared action controls are disabled native buttons, rendered solely from
  `available_actions`. They have no mutation handlers or forms. Status descriptions
  and role-union navigation are presentation, not authorization.

## Snapshot composition and failures

The detail loader reads detail/capabilities together and matches request ID,
version, department and evidence bindings: current pending approval, latest proposed
revision, active reversal and current resolution. Null trusted legacy resolution
IDs remain null. Duplicate/internal actions and assignment choices without an
assignment capability fail consistency checks. These checks can only suppress
supplied data, never grant additional actions.

On mismatch, one fresh pair of GETs is attempted. Persistent mismatch returns the
authorized detail with no capability names/choices/actions and a visible refresh
link. A capability 401/403/404 hides detail or returns to sign-in. Other capability
failures preserve explicit partial detail without capability display data. Evidence
groups load independently; access failures hide the detail, other errors show a
partial-evidence notice. GETs are no-store. No mutation is retried.

Queue sections retain their own empty/error state. Existing route loading boundaries
and section Suspense show loading states. Expiry/account-switch protections remain
in the existing SessionBoundary. Nothing sensitive is persisted in browser storage.
Capabilities describe a read snapshot, not a reservation or reusable grant; all
eventual mutations must still revalidate on the backend.

## Validation

Completed locally, without commits or pushes:

| Check | Result |
| --- | --- |
| `npm run test:frontend` | 15 passed |
| `.venv/bin/python scripts/test_web.py --max-failures=1 --retries=0` | 235 passed, no skips/retries, 6.2 minutes |
| `npm run typecheck` | Passed: generated contracts, web and browser test TypeScript |
| `npm run lint` | Passed, including new frontend tests |
| Production `npm run build` through the browser harness | Passed |
| `npm run contracts:check` | No drift |
| `node --test tests/contracts.test.mjs` | 7 passed |
| `.venv/bin/python -m pytest tests/unit/test_capabilities.py tests/unit/test_capability_api.py tests/unit/test_workflow_api.py -q` | 53 passed, 1 deprecation warning |
| `.venv/bin/ruff check tests/browser/serve.py` | Passed |
| `.venv/bin/ruff format --check tests/browser/serve.py` | Passed |
| `.venv/bin/mypy` | Passed, 91 source files |
| `git diff --check` | Passed |

The 235 browser checks include the existing 160 auth/design/foundation/login-security
checks and 75 new read integration checks (15 scenarios across desktop, laptop,
tablet, mobile and 320px). They use a disposable real PostgreSQL/Redis API and real
authentication. Controlled synthetic workflow read responses exercise action labels,
forbidden-action absence, multi-role behavior, participant-visible detail, names,
independent queues/holds, exact decimal rendering, paged choices, empty/error/partial
states, bounded stale refresh, evidence bindings, access revocation and tenant
rejection. Fixture-only response sequences and an event gate provide deterministic
stale/loading scenarios without sleeps. The read fixtures cannot override auth paths.

Added tests live in `tests/frontend/read-models.test.mjs` and
`tests/e2e/read-models.spec.ts`. `make test` now includes the dependency-free frontend
unit runner. The existing account-switch browser test now selects a private
expense/leave fixture, verifies backend 404 and checks the refreshed account/owned
list. Its former expectation that every employee-owned service request is hidden
from a manager conflicted with the already-authorized backend participant scope;
no workflow authorization was changed to accommodate the test.

New screens passed axe and horizontal-overflow checks at all five sizes. Added 25
macOS screenshot references for detail, approvals, service, finance and creation
options. Representative desktop/mobile/320px images were visually inspected.
Existing 6A screenshot references were not changed. The creation option references
were updated during implementation to include a visible list of available types,
since a disabled select alone does not let a reader inspect those choices.

Production API routes, services, schemas and generated contracts are unchanged.
The complete backend integration suite was not repeated for this frontend change;
selected backend/API regressions and the real-session browser journeys passed.
The initial browser checkpoint used macOS Chromium; subsequent Linux validation
is recorded below. Other-browser runs and manual screen-reader verification were
not performed. No hosted CI,
deployment, usability adoption or additional release gate is claimed. Non-failing
warnings concerned Node module/type-stripping discovery, color output and existing
Starlette/httpx deprecation notices.

## Final cross-platform validation

The approved implementation passed local Linux validation using Ubuntu 24.04
(Playwright `v1.63.0-noble`), native x64, Node 22.20.0, Playwright 1.63.0 and the
production Next.js build. The latest green hosted CI log confirms Ubuntu 24.04.5
with Node 22; this was a local container run, not a new hosted Actions run.

| Check | Final result |
| --- | --- |
| `npm run test:frontend` in Linux image build | 15 passed |
| `npm run typecheck` in Linux image build | Passed |
| `npm run lint` in Linux image build | Passed |
| `npm run build` in Linux image build | Passed |
| `npm run contracts:check` on host | Contracts match FastAPI OpenAPI |
| `playwright test tests/e2e/read-models.spec.ts --update-snapshots=changed --retries=0 --max-failures=1 --reporter=list,json` on Linux | 75 passed, 154.161 seconds; zero skips, failures or retries |
| `playwright test --retries=0 --max-failures=1 --reporter=list,json` on Linux | 235 passed, 415.012 seconds; zero skips, failures or retries |
| `git diff --check` | Passed |

Both browser runs covered desktop, laptop, tablet, mobile and narrow (320px).
The full run passed 47 tests per project, including delayed-hydration credential
safety. The disposable API used its own test database and real session handling.
It was stopped after validation. The full backend PostgreSQL/Redis suite was not
rerun: there are no backend production or generated-contract changes.

The first Linux run captured 25 temporary read-screen references; the second full
run compared all 25 without snapshot updates, using the unchanged screenshot
assertions and tolerance. References and JSON reports are outside the repository
under `/tmp/actiondesk-phase2-linux-final/`. macOS references remain unchanged.
Cross-platform PNGs differ with system fonts: all widths match and six full-page
heights differ through wrapping/font metrics. Representative desktop, mobile and
320px Linux images were inspected; no clipping or layout regression was found.
All five sizes passed the existing accessibility and horizontal-overflow checks.

Final source review confirms that only authentication POSTs are forwarded;
workflow POSTs stay blocked and no PATCH/DELETE entry points were added. Native
disabled action controls have no mutation handlers. Available actions come only
from backend capabilities/queue reads; roles orient navigation and statuses label
state or suppress inconsistent snapshots, never grant actions. API aliases still
use generated OpenAPI contracts. No application, test, dependency or screenshot
file changed during this validation; only this checkpoint record was updated.
No Linux-specific fix was required. No commits, pushes or mutation wiring were
performed.

## Before mutation wiring

Phase 3 requires separate authorization. Remaining work includes typed input forms,
CSRF, explicit idempotency keys, expected_version/evidence bindings, appropriate
confirmations, handling draft-create/submit partial success, backend-returned
results and safe conflict refresh. No action control in this checkpoint submits
or simulates a live workflow change. Synthetic design previews stay isolated.
