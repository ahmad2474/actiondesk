# Phase 1 milestone 3: deterministic manual workflows

Status: approved scope implemented and verified in unit tests and real PostgreSQL/Redis integration tests. No commit or push was performed. No milestone 4 work was started. This is not the full Phase 1 exit gate: workflow UI and correction/NEEDS_INFO revision semantics remain deferred.

## Authority and decisions

Read AGENTS.md, both governing PRDs with successful complete `pdftotext -layout` extraction, milestone 1/2 reports and the milestone 3 design before implementation. PRD v1.1 Sections 2, 4, 9, 10 and 16.1, 16.5–16.7 govern this milestone. The owner's explicit milestone 3 authorization supersedes the previous repository stop/approval hold. Milestones 1/2 and their live/CI acceptance are owner-confirmed; older sandbox limitations in those reports are historical.

Approved: deterministic forward states, conservative service cancellation before work starts, terminal leave approval, explicit-manager precedence, policy-controlled department fallback, one-of candidates, mandatory manager review for all expenses, finance review strictly above a configured threshold, separate decisions and processing, frozen submitted fields, participant visibility and explicit legacy assessment. A legitimately eligible non-requester can perform both approval roles and processing. No numeric threshold is selected by the application or migration. No default active policy is activated.

## Implementation

- `app.domain.workflow` defines typed forward edges. `transition_service.transition` is the transactional mutation entry point. Request creation keeps service SUBMITTED and expense/leave DRAFT. Submission writes SUBMITTED and MANAGER_REVIEW as two real updates/version increments/events within one transaction.
- Service routing requires department manager/admin; assignment requires an active same-department user with an active role. Only the assignee starts/resolves work; requester/admin closes with reason and timestamp. SUBMITTED/TRIAGED cancellation is requester-only, ASSIGNED cancellation requires manager/admin review; later cancellation is blocked.
- Expense/leave submission validates typed authoritative fields and a selected immutable policy. Currency support is explicitly PKR; money is a positive JSON Decimal string with at most two fractional digits and at most 16 integer digits. Leave dates must be ordered. Overlapping submitted/approved leave for the same requester is flagged, not denied.
- Mandatory manager step precedes finance when amount is strictly above the configured currency-specific threshold. Valid explicit employee-manager relationships take precedence; department fallback requires policy permission. Missing manager or finance candidates causes 409 and rolls back all submission writes.
- `approvals` remains a required-step projection. `approval_candidates` preserves routing source/user/role/requester snapshots. `approval_decisions` stores immutable actual-actor decisions linked to matching events. Legacy nominees are never replaced with decision actors. Rejection/withdrawal closes unacted steps as cancelled, preserving previous decisions.
- Decisions recheck current role, active user, tenant and recorded manager relationship. Only the current pending step is actionable. Ineligible candidates are never silently substituted. Requesters cannot approve/process their own expenses, including when holding manager/finance/admin roles. Admin alone grants no expense/leave approval authority.
- Expense APPROVED is separate from COMPLETED. Processing requires valid complete decision evidence, current finance role, non-requester processor, reason/reference and completion timestamp. No payment or other external effect is executed. Leave APPROVED is terminal.
- PostgreSQL request locks protect expected versions. Tenant/actor/key advisory locks also serialize exact retry keys across requests. `mutation_receipts` bind organization, actor, request, action and canonical payload hash and persist only outcome version/status and optional decision ID. No sensitive response/payload body is stored. Original expected versions can retry before stale-version checks; current authentication/visibility is still required. Retry responses contain the recorded compact outcome plus current authorized request detail.
- SQL visibility predicates filter before pagination. Owned requests remain the default list. Explicit `participant`, `assigned`, `triage` and `processing` scopes expose narrow work lists. Current eligible candidates, qualifying decision authors, service participants and finance processors can read applicable detail/history. Admin has no blanket expense/leave visibility.
- Cookie sessions, Argon2, CSRF/Origin checks, tenant Principal, login throttling, Redis/Celery, frontend and deployment configuration are unchanged. No notifications, analytics, AI, durable job/outbox dispatch, delegation/reassignment, reversal/reopen or correction/resubmission is introduced.

## API contract

`POST /requests/{request_id}/transitions` requires a UUID Idempotency-Key, authenticated cookie, allowed Origin and CSRF token. All actions include `expected_version` and nonempty `reason`. The body is discriminated by `action`:

| Action | Specific fields |
| --- | --- |
| submit | `data`, discriminated by `type`: expense requires vendor, amount, currency, purpose; leave requires start_date, end_date, leave_type |
| triage/start/close/cancel | No free-form data payload |
| assign | `assignee_id` |
| resolve | `resolution` |
| approve/reject | `approval_id` |
| process | `reference` |

No actor, organization, policy, threshold, bypass flag or arbitrary status is client-selectable. Extra input fields are forbidden. `route` is internal only. OpenAPI documents 401/403/404/409/422 problem responses and pagination. This endpoint does not introduce Redis throttling or a new 429 condition. `GET /approvals` returns actionable current steps, default limit 20/max 100/nonnegative offset. Default request lists remain owned; a work `scope` is explicit.

The approved `openapi-typescript` package remains the only TypeScript generator. Its discriminator handling mutates its input object, so the generator receives a structured clone; stored OpenAPI remains the actual FastAPI export. Repeated generation and input preservation are verified by the contract tests.

## Migration and historical data

`0004_workflows` adds workflow provenance, submission sequence, overlap/resolution/processing evidence, active policy selection, candidate/decision tables and compact receipts with tenant-qualified foreign keys. Policies, candidates, decisions, receipts and history are immutable. Guarded step projections require matching decisions or audited rejection/withdrawal closure. Submitted authoritative fields, policy references and durable completion attribution cannot be cleared or rewritten. Invalid state edges, forged decision evidence, incomplete approval, self-processing and invalid finance attribution are rejected by PostgreSQL as well as the service. The existing deferred version/history guard is retained.

Fresh disposable databases migrated to head, schema/metadata drift checks and migration/seed cycles passed. Legacy fixture history, nominees and existing policy definitions are preserved; no snapshots or decisions are fabricated and historical example thresholds are never activated. Historical expense/leave mutations are blocked until their missing evidence is resolved through a separately reviewed procedure. `python -m app.core.validate_legacy_approvals --organization-id '<UUID>'` performs a transaction-level read-only assessment and emits request IDs/evidence blockers only. Exit 1 indicates blocked evidence; it does not modify/activate any historical plan. The live test runs this command and verifies preservation. Downgrade refuses to discard managed workflow records or decision/receipt evidence.

The development database was not migrated during verification. The live suite used disposable databases created/dropped by the existing integration fixture inside the existing API container. Review the migration before applying it to the development database with `make migrate`.

## Explicit policy configuration

Policies are reviewed database configuration in this API-only milestone; there is no policy administration UI/endpoint. Choose organization, unique policy IDs, names, monotonically increasing versions and an actual approved threshold before activating a version. Do not update immutable policy definitions. A new version plus active selection preserves older requests' policy references.

Expense version 1 definition:

```json
{
  "schema_version": 1,
  "allow_department_fallback": false,
  "currency": "PKR",
  "finance_threshold": "<explicitly approved nonnegative decimal threshold>"
}
```

Leave version 1 definition:

```json
{"schema_version": 1, "allow_department_fallback": false}
```

Use reviewed parameterized SQL or a local psql transaction to insert the definition and select it. This template requires explicit psql variables; no example threshold is supplied and no policy was installed during this implementation:

```sql
BEGIN;
INSERT INTO approval_policies
  (id, organization_id, name, version, request_type, definition)
VALUES
  (:'policy_id'::uuid, :'organization_id'::uuid, :'policy_name', :'policy_version'::integer,
   'expense', jsonb_build_object(
     'schema_version', 1,
     'allow_department_fallback', :'allow_department_fallback'::boolean,
     'currency', 'PKR', 'finance_threshold', :'finance_threshold'));
INSERT INTO active_approval_policies (organization_id, request_type, policy_id)
VALUES (:'organization_id'::uuid, 'expense', :'policy_id'::uuid)
ON CONFLICT (organization_id, request_type) DO UPDATE SET policy_id=EXCLUDED.policy_id;
COMMIT;
```

For leave, insert a separate `request_type='leave'` policy with the leave definition and select that policy in its own type slot. Activate appropriate accounts/role assignments and manager relationships explicitly; seeds remain inactive/passwordless and do not create live approval plans. Absent/invalid policy or candidates is a safe submission conflict, not an approval exemption.

## Verification evidence

The required checks ran with existing installed dependencies; no manifest/lock changes or new libraries were needed. All final outcomes are recorded below. Test suites report only upstream Starlette/httpx and Alembic configuration deprecation warnings.

| Command | Result |
| --- | --- |
| `.venv/bin/ruff check apps tests scripts` | Passed |
| `.venv/bin/ruff format --check apps tests scripts` | Passed |
| `.venv/bin/mypy` | Passed |
| `.venv/bin/pytest tests/unit -q` | 100 passed |
| `CONTRACT_PYTHON=.venv/bin/python npm run contracts` | Passed; OpenAPI and TS regenerated |
| `CONTRACT_PYTHON=.venv/bin/python npm run contracts:check` | Passed; no drift |
| `CONTRACT_PYTHON=.venv/bin/python node --test tests/contracts.test.mjs` | 7 passed; no skips |
| `npm run lint` | Passed |
| `npm run typecheck` | Passed; contracts, web and check configuration |
| `make compose-check` | Passed; base and local Compose configuration |
| `git diff --check` | Passed |
| `docker compose --env-file .env -f infra/compose.yaml -f infra/compose.local.yaml exec -T api uv run --no-sync pytest tests/integration -q --maxfail=1 --tb=short` | 115 passed on real PostgreSQL/Redis |
| `docker compose --env-file .env -f infra/compose.yaml -f infra/compose.local.yaml exec -T api uv run --no-sync pytest tests/integration/test_workflows.py -q -k 'expense_threshold_and_processing or same_nonrequester or leave_terminal or legacy_fixture or completion_attribution' --maxfail=1 --tb=short` | 7 passed, 61 deselected; includes final timestamp/policy guards and transaction-level read-only legacy command |

The initial host `.venv/bin/pytest tests/integration/test_request_persistence.py` attempt was sandbox-blocked. With authorized escalation, host port 5432 refused connections because the existing PostgreSQL service has no host-published port. Verification therefore used the already running Compose API container and its PostgreSQL/Redis network. No port configuration was changed.

Coverage includes service/expense/leave happy paths, rejection and withdrawal, threshold exact/below/above boundaries, ordered dates/overlap flags, manager precedence/fallback/one-of candidates, missing policy/candidates, role/activity/relationship revocation, multi-role self-approval/admin bypass prevention, separate processing, participant/work-queue visibility, API discriminators and validation, real session/Origin/CSRF checks, rollback, exact retries with unchanged evidence, changed-input/request keys, stale/concurrent decisions, direct SQL edge/evidence/frozen-data bypasses, immutable decisions/history/receipts, downgrade preservation and legacy fixture assessment. Every integration fixture also executes Alembic upgrade twice and `command.check` against real PostgreSQL.

No CI run, full container rebuild/startup, browser workflow/UI test, development-database migration, policy activation, deployment, actual payment or complete Phase 1 gate is claimed. No commits were made.
