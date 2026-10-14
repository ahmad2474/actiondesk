# Phase 1 Milestone 3 — approved design

Status: explicitly approved by the project owner for this implementation. The approved decisions below supersede the earlier proposal/approval hold. Implementation and verification evidence are recorded in PHASE_1_MILESTONE_3.md. No milestone 4 or commit is authorized.

## Recommended architecture

Use one typed transition service, durable approval steps with immutable decision records, and one PostgreSQL transaction per mutation. Deterministic application rules own routing, eligibility, authorization, and outcomes. AI makes no workflow decisions.

The design follows PRD v1.1 and the existing request, tenant, authentication, and history foundations. Phase 1 Milestones 1 and 2 are complete according to the user's confirmation, including live verification and green GitHub Actions; older verification limitations in their reports are historical.

## Request state machine

Preserve the starting states:

- Service: `SUBMITTED`.
- Expense: `DRAFT`.
- Leave: `DRAFT`.

Use existing centralized enum values. Every accepted transition requires an immutable history event with actor, action, reason, UTC timestamp, and sequence, plus a one-step request version increment. No transition below has a reverse edge. Cancellation is a separate forward transition, never a silent reset.

An eligible approver is a recorded candidate who currently satisfies the required role, relationship, and tenant checks and is not the requester.

| Type | Source → target | Allowed actor | Required conditions |
| --- | --- | --- | --- |
| Service | `SUBMITTED → TRIAGED` | Department manager or admin | Same organization; valid department; recorded triage reason |
| Service | `TRIAGED → ASSIGNED` | Department manager or admin | Active assignee in the same organization and department |
| Service | `ASSIGNED → IN_PROGRESS` | Assigned user | Current assignment and active role |
| Service | `IN_PROGRESS → RESOLVED` | Assigned user | Resolution description required |
| Service | `RESOLVED → CLOSED` | Requester or admin | Explicit closure confirmation/reason; completion timestamp |
| Expense/leave | `DRAFT → SUBMITTED` | Requester | Valid typed fields; applicable policy; complete approval plan |
| Expense | `SUBMITTED → MANAGER_REVIEW` | Internal routing within submission | Mandatory manager step; configured threshold determines whether finance follows |
| Leave | `SUBMITTED → MANAGER_REVIEW` | Internal routing within submission | Valid manager step and candidates |
| Expense | `MANAGER_REVIEW → FINANCE_REVIEW` | Eligible manager approving | Persist manager decision; finance approval remains required |
| Expense | `MANAGER_REVIEW → APPROVED` | Eligible manager approving | No further required steps |
| Expense | `FINANCE_REVIEW → APPROVED` | Eligible finance approver | All earlier required steps approved |
| Leave | `MANAGER_REVIEW → APPROVED` | Eligible manager approving | Persist decision; terminal leave approval for this milestone |
| Expense/leave | Current review state → `REJECTED` | Eligible current-step approver | Mandatory rejection reason; close remaining pending steps |
| Expense | `APPROVED → COMPLETED` | Authorized finance user | Complete approval evidence; processing reason/reference; processor and completion timestamp |
| Service | `SUBMITTED/TRIAGED → CANCELLED` | Requester | Work has not started; no irreversible effects |
| Service | `ASSIGNED → CANCELLED` | Department manager or admin | Explicit review/reason; work has not started; no irreversible effects |
| Expense/leave | `DRAFT/SUBMITTED/MANAGER_REVIEW/FINANCE_REVIEW → WITHDRAWN` where applicable | Requester | No final approval, processing, or irreversible effects; reason required |

Submission and routing remain atomic, but perform two actual state updates with two version increments and two matching events. This preserves the existing deferred database history guard rather than skipping the submitted state.

Service requests have no financial-style approval. Leave approval is terminal for this milestone; there is no separate leave processing action. Expense approval never marks payment as processed and never initiates actual payment.

Approved conservative cancellation boundary: block service cancellation once work starts. The PRD's later manager-reviewed cancellation path needs reliable side-effect tracking before it can be safe. This restriction is approved. Final approval, completion, resolution, closure, rejection, and withdrawal never permit silent resetting. Reversal and reopening remain later work.

## Durable approval model

Reuse `approvals` as the required-step record. Add:

- `approval_candidates`: durable eligible user identities and routing source for each step; preserve the submitted candidate snapshot.
- `approval_decisions`: one immutable approve/reject decision per step, with actual actor, required role, decision timestamp, comment/reason, and linked request event.

Preserve existing nominated `approver_id` values. A legacy or fixed-nominee step retains its nominee; new candidate-pool steps may use a nullable nominee. Do not overwrite the nominee with the eventual decision actor. Store the actual actor in the decision record.

Approval status is a guarded projection of decision evidence or audited cancellation, not independent proof of approval. Rejecting or withdrawing closes unacted steps without rewriting earlier decisions or fabricating approval decisions. Only the current required step is actionable.

Protect decisions against update/delete. Preserve historical candidates and policy versions. No silent replacement of approval history.

## Self-approval and manager routing

Check `Principal.user_id != request.created_by` in the service and reinforce it with database constraints tied to the actual requester through organization/request/requester foreign keys. Multiple roles, admin status, and future delegation provide no exception.

Approved manager resolution:

1. Prefer the valid explicit employee-manager relationship.
2. Otherwise use valid department managers only when the selected policy explicitly permits that fallback.
3. With multiple department-manager candidates, require one approval, not all.
4. If no valid candidate exists, reject submission with a conflict and leave the request in draft; never auto-approve or select a special individual.

Resolve and persist candidates at submission. Recheck current roles, active user state, tenant membership, and applicable manager relationships when deciding. A later manager change must not silently add or replace candidates. If all recorded candidates lose eligibility, the request needs a future authorized reassignment path; this milestone must report the blocked condition.

Delegation and reassignment are deferred. Any future replacement must preserve the original chain and its audit evidence.

## Typed submission and monetary policy

Submission validates and freezes authoritative structured fields:

- Expense: vendor, positive Decimal amount represented as a JSON string, supported currency, and purpose.
- Leave: ordered start/end dates and leave type. Overlaps are flagged, not automatically denied.
- Service: existing request description; location remains optional according to the PRD.

Clients cannot choose trusted policy IDs, thresholds, approval stages, actors, or bypass flags. Do not use binary floating point or implicit currency conversion.

Reuse versioned approval policies, with explicit active selection unique per organization/request type and immutable definitions. Snapshot the selected policy and approval plan. Do not select an arbitrary policy row or rewrite an existing version.

Approved expense policy: manager approval for every expense, plus finance approval above a configured threshold for the supported currency. The PRD's 50,000/200,000 PKR values are examples, not universal accounting rules. Manager approval is required below and at the threshold as well. No numeric threshold is selected by this approval: it must be explicitly configured in the active versioned organization policy. There is no no-review exemption.

## Authorization and visibility

Preserve `Principal(organization_id, user_id)`. Every mutation rechecks current database roles, active user, organization, ownership, assignment/candidacy, and state inside the transaction. Sessions carry no trusted role claims.

- Owners submit and withdraw their own requests where the state permits it.
- Managers act within explicit relationship and policy scope.
- Finance approval and finance processing are separate permissions/actions.
- Admins may perform authorized service routing/closure, but cannot bypass approval eligibility or self-approval prevention.
- No client-supplied trusted actor or organization IDs.

Extend requester-only reads narrowly: participant-scoped detail/history, an actionable approval queue, and constrained assigned-service, triage, and finance-processing work lists. Apply tenant and sensitive expense/leave visibility checks to every response. Do not introduce blanket admin access to confidential request content.

## Minimum API contract

Use the existing transition-service convention rather than arbitrary status updates:

```http
POST /requests/{request_id}/transitions
Idempotency-Key: <UUID>
```

Illustrative typed approval body:

```json
{
  "action": "approve",
  "expected_version": 3,
  "reason": "Reviewed against the submitted policy",
  "approval_id": "00000000-0000-4000-8000-000000000001"
}
```

Use a discriminated action schema with action-specific fields. Actions: `submit`, `triage`, `assign`, `start`, `resolve`, `close`, `approve`, `reject`, `process`, and `cancel`. Approval actions identify the step. Assignment includes a target user ID as untrusted business input that the server validates. `cancel` maps to the appropriate service cancellation or expense/leave withdrawal state.

Responses include the updated authorized request/version and applicable decision outcome. Preserve existing cookie authentication, allowed-Origin checks, CSRF protection, and RFC 7807-style errors. Document unauthorized access, validation failures, invalid transitions, version conflicts, and idempotency conflicts. Never expose unrestricted `PATCH status`.

Add `GET /approvals` for the current actor's actionable steps, with pagination. Extend existing request reads only for authorized participants and the explicit work scopes above. Regenerate OpenAPI and TypeScript contracts.

## Concurrency and idempotency

Lock the tenant-scoped request row, then validate the expected version, action, and current authorization. Commit request changes, approval evidence, events, and the mutation receipt together in one PostgreSQL transaction.

Persist a mutation receipt unique on `(organization_id, actor_id, idempotency_key)`, binding the key to the request, action, and canonical payload:

- An exact retry returns the recorded outcome without new decisions or events, after current authentication and visibility checks.
- Reusing a key with a different request/action/payload returns `409`.
- Check an existing successful receipt before rejecting its original expected version as stale.
- Distinct concurrent mutations cannot consume the same version. The losing mutation returns an authorized `409` response.
- Uniqueness constraints prevent multiple decisions for the same step.

The existing history guard continues to require a matching event and exactly one version increment per state update. No transition silently overwrites another.

## Schema changes and safeguards

Approved migration scope:

- Approval candidate and immutable decision tables with tenant-aware foreign keys and uniqueness constraints.
- Guarded approval-step projections and links to audit events.
- Mutation receipts and their uniqueness/indexes.
- Frozen submitted fields and policy/plan evidence.
- History metadata needed to explain policy routing and decisions.
- Explicit active-policy selection and supporting indexes.
- Database guards against invalid state edges, editing frozen submitted data, clearing approval/completion evidence, duplicate decisions, and expense completion without required approval evidence and valid finance attribution.

Use database checks and service checks together. Database constraints cannot independently prove that an actor UUID came from the authenticated HTTP session; the trusted Principal boundary remains essential.

Historical seeds need explicit migration handling. Existing expense seed approvals all have manager steps, while higher-value expenses lack a complete future finance plan. Preserve their history and do not reinterpret those rows as complete live approval evidence. Validate legacy plans explicitly; block unsafe mutations of unvalidated legacy records rather than inventing decisions, actors, timestamps, or silently changing policy history.

## Test plan

- Every valid workflow transition and every invalid edge.
- Requester self-approval, multi-role self-approval, and admin bypass attempts blocked.
- Wrong-tenant actors, non-managers, inactive users, and revoked roles/relationships blocked.
- Employee-manager precedence, policy-controlled department fallback, multiple candidates, and missing-manager behavior.
- Decimal threshold boundaries, supported currency, ordered leave dates, and overlap flags.
- Finance-only processing; approval and processing remain separate; processor attribution preserved.
- Cancellation before final approval succeeds; cancellation after final approval or irreversible action fails.
- Exact retries create no duplicate decisions/events; changed-payload key reuse conflicts.
- Concurrent approvals and stale versions conflict safely on live PostgreSQL.
- Every transition records immutable history; failed transactions leave no partial request, approval, receipt, or event changes.
- Direct SQL attempts to bypass enforceable database invariants fail.
- Migration coverage, legacy-plan validation, and seed compatibility preserve historical evidence.
- Scoped detail/list/approval/work-queue reads prevent ID enumeration and sensitive-data leakage.
- Existing authentication, CSRF, and tenant tests continue to pass.

Implementation verification will include Ruff lint/format, mypy, unit and live PostgreSQL integration tests, contract generation/drift checks, TypeScript checks, applicable Compose configuration validation, and `git diff --check`. Report actual results and any blocked checks separately.

## Files likely to change after approval

- Domain transition, permission, and policy modules under `apps/api/app/domain/`.
- Transition service and scoped request queries under `apps/api/app/services/`.
- API routers and typed Pydantic schemas.
- SQLAlchemy models and Alembic migrations.
- Unit/integration tests and seed compatibility handling.
- Generated OpenAPI/TypeScript contracts under `packages/contracts/`.
- `AGENTS.md`, milestone notes, and an architecture decision record as needed.

Keep authentication architecture and Redis/Celery behavior unchanged. No frontend feature UI or new infrastructure is needed.

## Approved decisions

1. Approved deterministic state table, conservative service cancellation and terminal leave approval.
2. Approved explicit-manager precedence, policy-controlled department fallback and one-of candidates; missing candidates block submission.
3. Manager approval for every expense; finance above a configurable currency-specific threshold. No universal numeric threshold is authorized.
4. The same non-requester may approve as manager, approve as finance and process when legitimately eligible; separate durable evidence is mandatory.
5. Submitted fields are frozen. NEEDS_INFO, correction and resubmission remain deferred pending revision semantics.
6. Participant reads/work queues and explicit legacy evidence assessment are approved. No blanket admin visibility to expense/leave.
7. Typed discriminated actions replace the illustrative free-form `data` object above: only submit has typed expense/leave `data`; assignment, decisions, resolution and processing use specific required fields.

## Non-goals

No AI classification or routing, notifications/reminders, frontend workflow UI, delegation/reassignment, reversal/reopening, analytics/dashboard, SLA automation, actual payments, or AWS/deployment changes. Durable worker/outbox processing remains Phase 2 work.

Implementation is authorized only for milestone 3. Stop before milestone 4 and do not commit.
