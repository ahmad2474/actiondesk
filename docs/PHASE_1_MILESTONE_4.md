# Phase 1 milestone 4: audited expense/leave revisions

Status: approved scope implemented and verified in unit/API and real PostgreSQL/Redis integration tests. No commit/push or next milestone was performed. The development database was not migrated. Phase 1 frontend workflow UI and service clarification remain deferred.

## Authority and implementation

The owner's explicit implementation approval supersedes milestone 3's previous stop instruction. Phase 0 and milestones 1–3 are owner-confirmed accepted, migrated/live-verified, committed/pushed and CI green. Governing PRD v1.1 Sections 4, 9–10 and 16.1, 16.5–16.7, both successfully extracted PRDs, AGENTS.md, milestone 1–3 reports/design and ADR 0003 were reviewed during design. Approved decisions are recorded in PHASE_1_MILESTONE_4_DESIGN.md and ADR 0004.

- Typed request_changes is available only to a currently eligible candidate for the current actionable expense/leave step. Admin-only, broader manager scope, requester self-review, wrong tenant, revoked roles, inactive users and obsolete relationships provide no exception.
- request_changes enters NEEDS_INFO and closes pending steps as cancelled with immutable request_change_requests evidence identifying source submission/current approval/actual actor/event. Earlier decisions and candidates remain unchanged; correction closure is distinct from reject/cancel closure.
- Requester-only revise appends an immutable complete snapshot, predecessor/correction cycle, actual actor/time and same-state event/version increment. Expense/leave input reuses the existing strict field allowlists, Decimal-string/PKR and ordered-date validators. Clarification is nonempty and bounded to 20,000 characters. raw_text remains immutable original intake. Proposed snapshots do not replace submitted request_fields.
- Requester-only resubmit requires the latest revision from the current correction cycle. It validates the active versioned policy, resolves fresh current candidates, replaces the submitted projection and creates a new submission-scoped plan. Submission and internal route are two real updates/events/version increments in one transaction. Every resubmission restarts manager review, including explanation-only corrections. Finance is required strictly above the newly selected configured threshold; processing remains a separate non-requester finance action. Missing/invalid policy/candidates returns 409 without partial writes.
- Append-only request_revisions, request_submissions and request_change_requests bind snapshots, policy versions, actual actors and existing immutable history. Original submission_sequence stays fixed; current_submission_sequence advances. Existing null approval submission sequences refer only to the original milestone 3 plan. Current queues, ordering, decisions, closure, validation and final approval/completion evidence exclude historical plans.
- Leave overlap is recomputed per submission and recorded with its snapshot. Other NEEDS_INFO leave uses its last submitted dates; overlap is flagged, not automatically denied.
- Existing actor/tenant/key advisory locks, request row locks and compact immutable receipts retain expected-version/exact-retry behavior. Delayed correction retries cannot close a newer plan. Current identity/visibility remains required for receipt responses; no sensitive payload/response bodies are stored in receipts.
- Participant reads now restrict nomination-only visibility to the current plan, including during NEEDS_INFO. Superseded unacted nominees lose that access. Actual decision/correction authors retain active-role audit access; admin alone receives no sensitive expense/leave scope.

## API and contracts

POST /requests/{id}/transitions retains UUID Idempotency-Key, authenticated opaque cookie, Origin/CSRF, expected_version and nonempty reason. New discriminated inputs: request_changes(approval_id), revise(complete typed data, clarification), resubmit(revision_id). Extra actor/status/policy/candidate/bypass/patch inputs are forbidden. cancel permits requester withdrawal during NEEDS_INFO. No terminal reversal/reopen or service clarification action exists.

Request detail distinguishes submitted structured_fields from proposed_revision and exposes current submission/correction references. GET /requests/{id}/revisions uses limit 20 by default, maximum 100, and nonnegative offset; it returns scoped snapshots and related submission/policy-version/definition/approval/correction evidence. Sensitive snapshots are not duplicated into events or logs. Invisible/missing request IDs share 404. Existing sanitized RFC 7807 responses and request IDs remain in use.

OpenAPI and TypeScript contracts were regenerated from FastAPI with approved openapi-typescript. No handwritten TypeScript contract or converter is introduced.

## Additive migration and compatibility

0005_revisions adds nullable projection/plan links and three evidence tables, with tenant-qualified references, guarded submission projections, auditable NEEDS_INFO self-edges, current-submission decision/approval guards and immutable records. New history cannot substitute old approvals or unrelated revisions. PostgreSQL validates required current policy/candidate plans, immutable submitted snapshots, revision predecessors/correction cycles, actual eligible change-request actors, correction-linked pending closure and final current-plan approval/completion evidence.

Migration performs no historical snapshot/decision backfill or policy activation. Existing managed milestone 3 submissions continue through normal paths. On their first correction, lazy capture requires consistent trusted original history, fields/schema, policy, candidates and actual decision/projection evidence. The captured snapshot records the actual capture actor/time and references real original submit/route events; no original actor/timestamp is guessed. The live compatibility test constructs a real 0004 managed submission, upgrades it and verifies capture/resubmission without altering prior events. An inconsistent pre-upgrade field-schema probe returns 409 without new evidence or business-state changes.

Unvalidated historical workflow_version=NULL records remain blocked; the existing legacy assessment stays read-only. Downgrade refuses to discard new evidence. Empty/legacy-compatible downgrade/upgrade cycles restore original guards and preserve fixture history/nominees.

Review the migration before applying it to the development database using make migrate. Verification used only disposable migrated databases through the existing Compose API container. No development policy selection or migration was applied.

## Final validation evidence

Existing installed development/runtime dependencies were used; no dependency manifest/lock, image, infrastructure, authentication, worker or frontend workflow source change was needed.

| Exact command/check | Final result |
| --- | --- |
| `.venv/bin/ruff check apps tests scripts` | Passed |
| `.venv/bin/ruff format --check apps tests scripts` | Passed; 75 files already formatted |
| `.venv/bin/mypy` | Passed; 75 source files |
| `.venv/bin/pytest tests/unit -q --maxfail=1 --tb=short` | 150 passed; no skips |
| `docker compose --env-file .env -f infra/compose.yaml -f infra/compose.local.yaml exec -T api uv run --no-sync pytest tests/integration -q --maxfail=1 --tb=short` | 195 passed on real PostgreSQL/Redis; no skips; 185.21 seconds |
| Integration fixture migration checks | Every disposable fixture runs upgrade to head twice, checks expected revision and Alembic `command.check`; passed. Includes original/legacy upgrade and downgrade preservation probes |
| `.venv/bin/alembic upgrade head --sql > /tmp/actiondesk-milestone4-migrations.sql` | Passed offline SQL generation through 0005; live migration evidence is supplied by integration tests above |
| `CONTRACT_PYTHON=.venv/bin/python npm run contracts` | Passed; actual FastAPI OpenAPI and TypeScript regenerated |
| `CONTRACT_PYTHON=.venv/bin/python npm run contracts:check` | Passed; no drift |
| `CONTRACT_PYTHON=.venv/bin/python node --test tests/contracts.test.mjs` | 7 passed; no skips, including reproducibility and negative drift/tampering checks |
| `npm run lint` | Passed |
| `npm run typecheck` | Passed; contracts, web and check configuration |
| `git diff --check` | Passed |

Final suites reported only upstream Starlette/httpx and Alembic configuration deprecation warnings. Initial iterations exposed FK deferral/flush ordering, lazy-capture SQL alias, empty downgrade ordering, and a routing guard that still inspected historical candidates; these were fixed and covered before the final complete runs. Early combined sandbox Docker invocations were denied; approved escalated reruns succeeded. No requested check remains blocked.

Coverage includes all expense/leave correction stages, explanation-only full reapproval, all nine below/at/above amount changes, multiple revisions/cycles, latest-proposal enforcement, missing policy/candidates, active policy/manager changes, current role/activity/relationship checks, self/multiple roles, withdrawal/terminal restrictions, participant and former-nominee visibility, real sessions/CSRF, exact and delayed retries, live concurrent same/different-key mutations and competing actions, rollback fault injection, immutable old/current evidence, SQL bypass attempts with and without forged history, fresh migration/model drift, actual milestone 3 lazy capture, incomplete-evidence rollback and downgrade preservation. Existing service/auth/Redis tests remain included.

No new CI run, full stack rebuild/startup, development-database migration, browser/UI verification, deployment, actual payment or complete Phase 1 exit gate is claimed. No commit/push or next milestone work was performed.

## Changed areas

Domain workflow/actions; typed API/read schemas and request router; SQLAlchemy models and new reviewed migration; transition/policy/read/visibility services; generated contracts; shared revision cases, unit/API and live constraint/concurrency/compatibility tests; engineering/readme/authorization documentation and ADR 0004. Existing migration files and authentication/session/CSRF/Redis/Celery architecture remain unchanged.
