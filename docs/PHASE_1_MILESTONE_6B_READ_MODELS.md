# Milestone 6B Phase 1: capability and read-model foundation

Owner-confirmed complete, committed/pushed and CI green. The scope and validation
below record that checkpoint. Subsequently authorized frontend consumption is
tracked in [the Phase 2 checkpoint](PHASE_1_MILESTONE_6B_FRONTEND_READS.md).

Scope: explicit owner authorization after completed, committed/CI-green 6A and
security maintenance. This checkpoint implements backend-authoritative read
contracts only. No UI redesign, workflow buttons, new mutations, dependencies,
migrations, AI, notifications, uploads, analytics or deployment. No commit/push.
See [ADR 0007](adr/0007-workflow-capability-reads.md) for the architectural decision.

## Additive API shape

All endpoints use the unchanged authenticated Principal, scoped PostgreSQL reads,
RFC 7807 errors and X-Request-ID. Authenticated responses are no-store and vary on
Cookie while retaining existing CORS Origin variation. Pagination bounds remain
limit 1–100 / offset ≥0; default choices limit 50, queues limit 20.

### `GET /requests/{request_id}/capabilities?limit=50&offset=0`

```json
{
  "request_id": "<authorized request UUID>",
  "expected_version": 3,
  "evaluated_at": "<database UTC timestamp>",
  "organization_timezone": "Asia/Karachi",
  "available_actions": [
    {"action": "approve", "approval_id": "<current approval UUID>"},
    {"action": "reject", "approval_id": "<current approval UUID>"},
    {"action": "request_changes", "approval_id": "<current approval UUID>"}
  ],
  "blocking": [],
  "department": {"id": "<request department UUID>", "name": "Operations"},
  "participants": [{"id": "<authorized participant UUID>", "name": "Current display name"}],
  "assignee_choices": null
}
```

The example omits nullable unused action-binding fields for brevity; the actual
contract serializes those fields as null. Available names match existing transition
actions: submit, triage, assign, start, resolve, close, approve, reject, process,
cancel, request_changes, revise, resubmit, request_reversal, approve_reversal,
reject_reversal, create_correction, reopen. Internal route is never advertised.
Bindings include approval_id, latest revision_id, active reversal_request_id and
actual resolution_id where applicable. Old managed resolutions without a persisted
ID return null, never a fabricated ID; the existing typed reopen action permits it.

`limit/offset` page assignment choices only. Choices are null unless assignment is
currently allowed; otherwise they contain `{items:[{id,name}],limit,offset,has_more}`.
No emails, broad roles/directory results, policy definitions/thresholds, hidden
candidate failure messages or arbitrary actor/policy/bypass inputs are introduced.
Missing/invisible/cross-tenant request IDs return the same 404. Invalid organization
timezone/configuration returns a safe 409, not a UTC fallback.

A capability describes what the actor may currently **attempt**, not guaranteed
acceptance or a reusable authorization grant. Typed form fields still need to be
supplied. Draft submission checks policy/manager readiness without fabricating
expense/date values; finance-threshold routing is validated once actual fields are
provided. Resubmission already has a latest immutable proposal and therefore checks
its exact data, current policy/candidates and overlap evidence before advertising.
The UI must compare the separate detail.version and capability.expected_version
and refresh mismatches before presenting action bindings. Mutations always recheck.

### `GET /requests/options?limit=50&offset=0`

Returns `{organization_timezone, request_types, departments:{items,limit,offset,
has_more}}`. Departments are precisely the current creation choices inside the
Principal tenant, using a selector shared with create_request. Existing creation
permits any existing same-tenant department for an active principal. This endpoint
does not change that policy, enumerate users, or expose another organization's
configuration. The static options route precedes the dynamic UUID route.

### `GET /work-queues/{queue}?limit=20&offset=0`

`queue` is one of approvals, reversals, service_work, finance_processing. Response:
`{queue, organization_timezone, evaluated_at, items, limit, offset, has_more}`.
Each item contains request ID/type/title/status/version, requester/department and
optional assignee ID/name, created/updated/due timestamps, current submission/work
cycle identities, allowed actions/bindings and safe blockers. Expense amount stays
a decimal string; leave dates stay date-only. No raw intake, purpose, revision
text, internal policy or broad candidate list is included in summaries. Existing
request detail now also returns the persisted due_at rather than requiring a
fabricated frontend display value.

- Approvals: current actionable step/current snapshotted candidates only, with full
  current-plan/decision validation; later or historical nominations cannot act.
- Reversals: active review, eligible final-step candidate, independent from requester
  and initiator. Expired leave acceptance disappears; denial can remain available.
- Service work: currently visible assigned work or current managed/admin department
  service work in active/resolved/reopened states. A visible item can have no action;
  service participants do not receive hidden expense/leave data.
- Finance: independently authorized current approved expenses, excluding self;
  reversal-held visible expenses remain listed with processing_on_hold semantics
  (`blocking.code = reversal_review`), without a process action.

Sort is existing-style FIFO created_at then ID, with no unsupported search or
filters. Tenant and participant predicates run before row selection, then shared
preflight checks run before effective offset/limit. `has_more` counts only eligible
items; there are no fake totals or page holes caused by filtering after pagination.
The streaming candidate scan trades some queries for correctness; it is not a
claim of constant-cost pagination for large future datasets.

## Exact authorization reuse

`action_checks.check_action` runs on new mutations after the existing row lock,
version check and Principal validation, and on capability reads without locks.
The mutation dispatcher no longer contains separate process/cancel/triage/assign/
close authorization branches. Mandatory typed payload validation remains in the
existing action schemas/handlers; no arbitrary status PATCH is added.

Shared helpers:

- `validated_steps`, `actionable_step`, `candidate_eligible`, `active_roles`,
  `department_manager`: immutable current submission/plan/decision evidence and
  current tenant/user/role/relationship eligibility. No candidate substitution.
- `resolve_plan(lock=...)`, `latest_proposal`, `revision_base`, `submission_overlap`:
  active immutable policy/fresh candidate plan, current correction cycle/latest
  proposal, trusted predecessor, existing leave-evidence checks. No read persistence.
- `check_request_reversal`, `check_decide_reversal`, `check_create_correction`:
  complete final-step evidence, expense/leave boundary, independent initiator/
  decider rules, accepted correct-intent source and exactly one replacement.
- `resolution_evidence`, `check_reopen`, `valid_assignee`: current/legacy trusted
  resolution, active immutable bounded reopen policy, inclusive expiry, retained
  current assignee. Evidence inspection is separate from lazy capture/writes.
- `assignee_query`/`require_assignee` and `department_choices`: identical choice and
  write-validation boundaries. Existing reversal queue SQL uses the new shared
  `reversal_predicate` too.

Mutations still recheck binding IDs, versions, roles/relationships and time under
locks; business/evidence/receipts remain one transaction with unchanged DB guards.
Exact retries skip new preflight just as before, preserving original receipt
semantics and current authenticated visibility. Capabilities are not cached grants.
Approval and processing stay separate; requester self-review/processing and
initiator self-decision remain impossible, including multi-role/admin cases.

## Read integrity, names and compatibility

New reads use PostgreSQL repeatable-read/read-only transactions with a database
observation timestamp. Session authentication maintenance remains unchanged in
its separate existing path. No business INSERT/UPDATE/DELETE, FOR UPDATE/SHARE,
plan/receipt/event creation, lazy capture or manufactured historical values occurs
on these GETs. The SQLite adapter isolates unit tests only; live tests verify the
PostgreSQL behavior.

Display labels are current names for already-authorized request/history/current-
plan IDs, including requester, assigned/processing actors and actual event authors.
They are not historical name snapshots. Unrelated same-tenant users and foreign
users never become detail participants; superseded unacted candidates gain neither
access nor a new name lookup through the old nomination. Assignment choices are a
separate expressly authorized department-scoped form choice set. Admin alone still
has no sensitive expense/leave visibility.

No schema migration/backfill is needed. Old trusted Milestone 3 approvals and
Milestone 4 service resolutions may be inspected without compatibility writes;
actual authorized mutations retain lazy capture. Incomplete evidence suppresses
the relevant action and never repairs history. Existing legacy service forward
behavior remains compatible; reopening requires trusted managed evidence. The
legacy integration fixtures now explicitly assert that capability reads leave
submission/revision/resolution evidence absent until the real mutation.

## Tests added

`tests/capability_cases.py` defines **24 parameterized acceptance cases**, run through
both `tests/unit/test_capabilities.py` and live
`tests/integration/test_capabilities.py`:

- owner drafts; current manager/finance step visibility; forbidden/admin/tenant
  absence; stale role, future grant, inactive actor and changed manager relationship;
- multi-role requester exclusions; one non-requester separately approving both
  steps and processing; terminal completion;
- revise/resubmit latest proposal, fresh plan and amounts below/at/above the
  configured threshold; revoked finance eligibility; missing active policy;
- final-step-only reversal initiation; independent alternate finance review;
  single-candidate initiator blocking; correction availability exactly once;
- leave start boundary in Asia/Karachi; denial remains after acceptance expires;
- service actors/choices/start/resolve/close; configured reopen policy and inclusive
  microsecond boundary; invalid retained assignee; terminal closed requests;
- participant/creation-option isolation, no unrelated user names/emails/roles,
  all foreign queues empty; stale capability cannot authorize a later mutation;
- authorized queue pagination, exact decimal summary and excluded sensitive fields;
- fresh-manager resubmission with historical decisions non-actionable; inactive or
  role-revoked assignees excluded; superseded unacted finance access disappears;
- zero business DML/row-lock statements and unchanged table counts across reads.

`tests/unit/test_capability_api.py` adds **10 API checks** (including pagination
parameterizations): typed action IDs, request/queue/options visibility, unavailable
POST/global-directory routes, forged identity headers ignored, auth required,
invalid bounds, safe problems, no-store and preserved CORS variation, and OpenAPI
exposing only approved GET inputs. Existing route/contract inventories explicitly
add exactly the three approved reads. Two existing live compatibility tests gain
pre-mutation no-capture assertions (including valid/corrupt service parameterizations).

## Validation

All requested checks completed; none remain blocked.

| Check | Exact final result |
| --- | --- |
| `.venv/bin/python -m pytest tests/unit -q` | **238 passed**, 1 warning, 45.29s |
| `docker compose --env-file .env -f infra/compose.yaml -f infra/compose.local.yaml --profile checks run --rm checks` | **316 passed**, 977 warnings, 378.44s; real PostgreSQL/Redis, migration/model checks, SQL bypass and concurrency regressions |
| `CONTRACT_PYTHON=.venv/bin/python node --test tests/contracts.test.mjs` | **7 passed**, 0 skipped, 20.96s |
| `CONTRACT_PYTHON=.venv/bin/python npm run contracts` | Regenerated OpenAPI and transport types with approved openapi-typescript |
| `CONTRACT_PYTHON=.venv/bin/python npm run contracts:check` | Passed; artifacts match FastAPI OpenAPI |
| `.venv/bin/ruff check apps tests scripts` | Passed |
| `.venv/bin/ruff format --check apps tests scripts` | **91 files already formatted** |
| `.venv/bin/mypy` | Passed, **91 source files** |
| `npm run typecheck` | Passed: generated contracts, web/route types, check scripts |
| `npm run build` | Passed, Next 16.4.1 production webpack build |
| `npm run lint` | Passed |
| `git diff --check` | Passed |

Development verification caught an extracted correction-link binding reference,
the intentionally expanded route inventory, and two new tests' incorrect CORS
header/origin assumptions. These were corrected before the final green runs.
Vary now preserves Origin and adds Cookie; no auth origin allowance was widened.
Warnings are existing Starlette/httpx and Alembic path-separator deprecations.
No warnings were suppressed. Backend SQL/schema/migration guards remain unchanged.

The full browser/screenshot suite was not repeated in this backend-only foundation
step; no UI or browser-test/screenshot artifacts changed. The requested frontend
build/lint/typecheck passed. No hosted CI run, commit/push or deployment is claimed.

## Remaining work before live mutation wiring

The current frontend adapter and owned-detail composition intentionally remain
unchanged in this first backend step. Next 6B work must explicitly allow these
read routes, compose participant detail/capabilities at matching versions, use
paged authorized choices, and render only available server action names. Then wire
existing typed mutations with CSRF, an explicit idempotency key, expected_version,
consequence-specific confirmations, server-returned results, safe 409 refresh and
no optimistic authorization/status changes or automatic mutation retry.

There is no new missing directory, capability or transition endpoint required for
the approved request/approval/service/finance forms. Draft field validation remains
part of submit; there is no separate draft PATCH/save API to pretend exists. New
request creates a real draft before expense/leave submission; partial success must
be handled explicitly in UI wiring. No global search, policy editing, assignment
replacement, delegation, notification or other unapproved API is implied.

## Files changed

- `AGENTS.md`
- `README.md`
- `apps/api/app/api/requests.py`
- `apps/api/app/api/reversals.py`
- `apps/api/app/api/work_queues.py`
- `apps/api/app/main.py`
- `apps/api/app/schemas/capabilities.py`
- `apps/api/app/schemas/core.py`
- `apps/api/app/services/action_checks.py`
- `apps/api/app/services/capabilities.py`
- `apps/api/app/services/eligibility.py`
- `apps/api/app/services/lifecycle.py`
- `apps/api/app/services/policies.py`
- `apps/api/app/services/requests.py`
- `apps/api/app/services/transition_service.py`
- `apps/api/app/services/visibility.py`
- `docs/PHASE_1_MILESTONE_6B_READ_MODELS.md`
- `docs/adr/0007-workflow-capability-reads.md`
- `packages/contracts/openapi.json`
- `packages/contracts/src/api.d.ts`
- `tests/capability_cases.py`
- `tests/contracts.test.mjs`
- `tests/integration/test_capabilities.py`
- `tests/integration/test_lifecycle.py`
- `tests/unit/test_capabilities.py`
- `tests/unit/test_capability_api.py`
- `tests/unit/test_foundation.py`
