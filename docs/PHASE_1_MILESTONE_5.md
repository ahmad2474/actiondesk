# Phase 1 Milestone 5: Reversal and service reopening

Owner status: complete, committed/pushed and CI green, as confirmed before Milestone 6A. The implementation-pass observations below are historical.

Scope: owner-approved implementation only, under PRD v1.1 Sections 16.1–16.7 and [ADR 0005](adr/0005-request-lifecycle.md). Phase 0 and milestones 1–4 are owner-confirmed complete, committed/pushed and CI green. These milestone 5 changes are local and uncommitted; no push, deployment or next milestone is authorized.

## Behavior and authorization

| Request | From | Action | To | Authority and boundary |
| --- | --- | --- | --- | --- |
| Expense/leave | APPROVED | request_reversal | REVERSAL_REVIEW | Owner or current eligible final-step snapshot candidate; expense unprocessed; leave strictly before local start date |
| Expense/leave | REVERSAL_REVIEW | approve_reversal | REVERSED | Independent current eligible final-step candidate; neither owner nor initiator; recheck reversal boundary |
| Expense/leave | REVERSAL_REVIEW | reject_reversal | APPROVED | Same independent eligibility; preserves original approved_at and approval decisions |
| Expense/leave | REVERSED | create_correction | REVERSED plus new DRAFT | Owner only, accepted correct intent, one direct replacement; source only receives an audit event |
| Service | RESOLVED | reopen | REOPENED | Owner, current department manager or admin; explicit valid active policy; retained valid assignee |
| Service | REOPENED | start | IN_PROGRESS | Retained assignee; current active user, department and role |
| Service | IN_PROGRESS | resolve | RESOLVED | Assignee; new immutable resolution bound to current cycle |
| Service | RESOLVED | close | CLOSED | Existing owner/admin rule; current-cycle resolution required |

COMPLETED expense and CLOSED service remain terminal. Leave initiation/acceptance on or after start_date is forbidden in current organization timezone. Review blocks finance processing; denial restores the existing approval rather than creating a vote. A blocked independent review has no substitution/admin bypass. Original submitted fields, policy, candidates, decisions, approved_at, resolutions and completion evidence remain immutable.

Correction children preserve tenant, owner, type, department, title, raw intake provenance and due_at. They receive new request identity and require their own typed submission under current policy and freshly resolved candidates. No source approval satisfies the child; source access does not confer child access. Raw intake remains frozen.

## Persistence and compatibility

Additive migration `0006_lifecycle` adds append-only `request_reversal_requests`, `request_reversal_decisions`, `request_correction_links`, `service_resolutions`, `service_reopenings`, and `service_reopen_policies`, plus a mutable organization active-policy selector. Tenant-qualified foreign keys, unique source/child/reversal/cycle constraints, immutable triggers and deferred matching-event guards prevent bypass. Guarded request pointers track active reversal, service cycle and latest resolution. Receipt `related_request_id` records the correction child's identity. Revision kind `approval_capture` identifies trusted capture of an original managed approved submission.

There is no migration backfill or default-policy activation. Original managed milestone 3 approvals can be lazily bound to submission/revision evidence only after validating their existing fields, policy, plan, candidates, events and decisions. Original managed service resolutions can be captured on reopening only with matching real start/resolve actor, timestamp and stored resolution. Capture attribution is separately recorded; historical values are not invented. Incomplete/inconsistent evidence returns 409 and rolls back all writes. Legacy unvalidated records cannot enter the new paths. Existing pre-milestone service forward/close paths remain compatible.

Downgrade refuses when lifecycle evidence, policies, pointers or reversal states exist. Empty downgrade restores milestone 4 guards; enum labels remain because PostgreSQL cannot safely remove enum values in place. New enum labels are committed before their use in guard functions, so migration is repeatable but is not one all-or-nothing transaction across that enum boundary.

## API and visibility

All mutations remain `POST /requests/{request_id}/transitions` through the existing transition service, authenticated Principal, session, CSRF, UUID Idempotency-Key and expected_version contract. Every action requires bounded reason. New typed bodies:

- `request_reversal`: `intent` (`withdraw` or `correct`).
- `approve_reversal` / `reject_reversal`: current `reversal_request_id`.
- `create_correction`: accepted current `reversal_request_id`.
- `reopen`: optional latest `resolution_id`; omit for trusted original-resolution lazy capture.

No actor, role, organization, state, policy, timestamp or bypass input is accepted. Existing actions cannot edit submitted approved sources. `outcome.related_request_id` returns the same child on exact correction retries. Outcomes remain the original receipt while request detail reflects current authorized state.

`GET /reversals` paginates only actionable independent current candidates. `GET /requests/{request_id}/lifecycle` returns separately bounded, event-ordered reversal requests/decisions/resolutions/reopenings; join their sequence to immutable request history for reason, actor and chronology. Detail includes latest reversal/decision/current-cycle resolution and independently visible correction IDs. After reopen, detail hides the prior resolution as a current result until the new cycle resolves; history retains it.

Requester/current participant/active-role audit scopes apply. Admin alone receives no sensitive expense/leave visibility. Finance retains approved-expense hold visibility to explain processing conflicts, with no reversal decision authority. Reversal decision authors retain active required-role audit access. Cross-tenant IDs remain concealed.

## Locking, retries and database guards

Existing per-actor/tenant idempotency advisory locks and request row locks serialize competing mutations. Current user/role/relationship checks and active configuration reads are locked. PostgreSQL clock_timestamp is sampled after request locking for new time-sensitive actions. Missing candidates or policy fails with no partial writes. Expected-version mismatch conflicts; changed payload/key reuse conflicts. Exact retries do not duplicate evidence or alter later state and still require current authentication/visibility.

Reversal versus processing, accept versus deny, reopen versus close and concurrent correction creation have one durable winner. Unique constraints provide a second defense. Historical approval/candidate identities are bound to the current approved submission; current service cycle resolution is required for closure. SQL guards reject matching-history bypasses, initiator self-review, altered pointers/provenance, missing current resolution, expired backdated reopening and mutation/deletion of evidence. Application boundary evaluation is inclusive; commit guards additionally reject expiry/date crossing before commit.

## Explicit pilot configuration

The approved pilot duration is **604800 seconds (7 days)**. No policy is created or activated automatically by this implementation or migration. After migration, an authorized database operator can provision the selected organization explicitly using the following transactional psql template. Supply real organization UUID, a fresh policy UUID and a chosen next version; it is intentionally not an application workflow endpoint. Existing immutable versions must never be overwritten.

```sql
BEGIN;
INSERT INTO service_reopen_policies
  (id, organization_id, name, version, definition)
VALUES
  (:'policy_id'::uuid, :'organization_id'::uuid, 'pilot-service-reopen',
   :'policy_version'::integer,
   '{"schema_version":1,"window_seconds":604800}'::jsonb);
INSERT INTO active_service_reopen_policies (organization_id, policy_id)
VALUES (:'organization_id'::uuid, :'policy_id'::uuid)
ON CONFLICT (organization_id) DO UPDATE SET policy_id = EXCLUDED.policy_id;
COMMIT;
```

Policy schema accepts an integer duration from 3600 to 2592000 seconds. Expiry is inclusive from the latest actual resolution, never from a retry or old cycle. Absent/invalid policy gives 409. No development organization was selected or configured during this work.

## Validation

Final local validation passed. Tests cover independent review and multi-role owners/initiators, role/relationship revocation, local leave boundaries, denial preservation, current policy/fresh replacement review, copied due/provenance, linked visibility, repeated service cycles, invalid/missing policy and retained assignee, inclusive expiry, stale versions, delayed/exact retries, concurrent competing/same-key writes, injected rollback, immutable tables, direct SQL bypasses, real sessions/CSRF, old managed capture, inconsistent capture rejection and downgrade refusal. Existing milestone tests remain part of the full suite.

### Exact check results

| Check | Result |
| --- | --- |
| Ruff lint: `.venv/bin/ruff check apps tests scripts` | Passed |
| Ruff formatting: `.venv/bin/ruff format --check apps tests scripts` | Passed; 81 files formatted |
| Strict mypy: `.venv/bin/mypy` | Passed; no issues in 81 source files |
| Unit/API: `PYTHONPATH=apps/api:apps/worker .venv/bin/pytest tests/unit -q --maxfail=1 --tb=short` | 203 passed in 36.28 seconds |
| Full live PostgreSQL/Redis: Docker API container `uv run --no-sync pytest tests/integration -q --tb=short` | 292 passed in 301.76 seconds |
| Stricter competing-action assertions: Docker `pytest tests/integration/test_lifecycle.py -q -k competing_lifecycle --tb=short` | 3 passed, 94 deselected in 3.82 seconds; every loser is 409 |
| Migration/model drift | Passed in every disposable integration fixture: upgrade head twice and Alembic check; table/FK/constraint/index comparison, empty downgrade/base/upgrade and lazy M3 compatibility tests passed |
| Offline migration generation: Docker `alembic upgrade head --sql` | Passed; 2219 lines generated into temporary SQL artifact |
| Contract generation: `CONTRACT_PYTHON=.venv/bin/python npm run contracts` | Passed with approved openapi-typescript |
| Contract drift: `CONTRACT_PYTHON=.venv/bin/python npm run contracts:check` | Passed; artifacts match FastAPI |
| Contract tests: `node --test tests/contracts.test.mjs` | 7 passed, 0 failed |
| TypeScript: `npm run typecheck` | Passed for contracts, web and checks |
| TypeScript/web lint: `npm run lint` | Passed |
| `git diff --check` | Passed |

No required checks are blocked. The unit run emitted one Starlette/httpx deprecation warning; the live suite emitted 905 Starlette/httpx and Alembic prepend_sys_path deprecation warnings. These did not fail checks. No dependency/config expansion was made solely to suppress them. An initial live run stopped because the existing foreign-organization follow-up test expected only a foreign-key failure; the new immutable-provenance guard rejects earlier. Its assertion now accepts either database guard, and the full rerun passed. The race assertion was subsequently tightened and all three affected live cases rerun successfully.

## Non-goals and operational limits

No refunds, adjustments, payments, payroll/calendar undo, completed-expense correction, retrospective leave reversal, closed-service reopen, delegation/reassignment, service clarification, AI decisions, notifications, frontend workflow UI, analytics/SLA, AWS/deployment or Phase 2 async work. Authentication/session/CSRF and Redis/Celery architecture remain unchanged; no dependencies added. Test migrations use disposable databases. The development database has not been migrated by this work; no CI, deployment or commit/push result is claimed.
