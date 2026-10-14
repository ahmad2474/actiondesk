# Phase 1 Milestone 4: approved revision design

Status: explicitly approved by the project owner. Scope ends at milestone 4; no commit or next milestone is authorized. Governing authority is PRD v1.1 Sections 4, 9–10 and 16.1, 16.5–16.7, plus the owner's approved milestone 3/4 policies. Both PRDs and milestone 1–3/ADR 0003 documents were read during the design review; PDF extraction succeeded.

## Lifecycle and actors

| Type | Source | Action | Target | Actor |
| --- | --- | --- | --- | --- |
| Expense | MANAGER_REVIEW/FINANCE_REVIEW | request_changes | NEEDS_INFO | Current actionable recorded candidate, still eligible |
| Leave | MANAGER_REVIEW | request_changes | NEEDS_INFO | Current actionable recorded manager candidate, still eligible |
| Expense/leave | NEEDS_INFO | revise | NEEDS_INFO | Requester |
| Expense/leave | NEEDS_INFO | resubmit | SUBMITTED | Requester; latest proposal in current correction cycle |
| Expense/leave | SUBMITTED | internal route | MANAGER_REVIEW | Same resubmission transaction |
| Expense/leave | NEEDS_INFO | cancel | WITHDRAWN | Requester |

Current tenant, active-user, role, relationship and requester separation checks remain mandatory. No broader manager/admin correction authority. No service clarification. approve/reject/process cannot execute in NEEDS_INFO. No terminal revision/reversal/reopen edge is added. Existing review rejection and separate finance completion continue.

request_changes closes pending steps as cancelled through linked immutable correction evidence. Prior approved steps/decisions remain unchanged. Resubmission creates a fresh plan; old decisions cannot authorize the new submission, even if only clarification changed. Manager approval is always required; finance approval is strictly above the currently selected configured threshold. Missing/invalid active policy or candidates yields 409 and no partial writes.

## Evidence and content

Append-only request_revisions records complete typed snapshots, predecessor, correction cycle, originating event, actor and UTC timestamp. Expense allowlist: vendor/amount/currency/purpose, with existing Decimal-string/PKR validation. Leave allowlist: start_date/end_date/leave_type, with ordered dates. Clarification is a separate nonempty bounded field, maximum 20,000 characters. raw_text remains original intake; department/type/owner/title/assignment/due date/processing evidence are not revision inputs. Submitted request_fields and proposed snapshots stay separate until audited resubmission.

Append-only request_submissions binds a snapshot, immutable policy, submit/route sequences and overlap result. request_change_requests binds the correction event to its source submission/current step and actual eligible candidate. Plans retain immutable identities; pending closure remains distinguishable through the correction link. Existing original submission_sequence stays fixed; current_submission_sequence advances. Null approval submission_sequence denotes the original milestone 3 plan; new plans have explicit event sequences. Every query/guard uses the current effective sequence.

Select the active policy again at resubmission and snapshot fresh candidates from current roles/users/relationships. Preserve previous versions/plans; no candidate replacement in an existing plan. Recompute leave overlap, including last submitted dates of other NEEDS_INFO leave; flag, never automatically deny.

## Transactions, APIs and visibility

Use transition_service.transition exclusively. Each request_changes/revise/cancel advances one version with a matching immutable event. resubmit and route advance two versions/events atomically. Same-state revisions are permitted only with matching proposal evidence. Row locks and actor/tenant/key advisory locks retain existing optimistic versioning and receipt semantics. Exact retries return historical compact outcome plus current authorized detail; changed payload/key reuse conflicts; failed transactions retain no receipt.

Extend POST /requests/{id}/transitions with typed request_changes(approval_id), revise(data,clarification), resubmit(revision_id), each requiring expected_version/reason and UUID Idempotency-Key. Client actors, statuses, policies, candidates and bypass inputs remain forbidden. Authenticated Principal/cookies/Origin/CSRF/session architecture stays unchanged. Add paginated GET /requests/{id}/revisions for scoped snapshot/submission/correction/approval evidence and policy versions. Generate contracts from FastAPI via approved openapi-typescript.

Requesters see their own evidence. Current eligible candidates see current content/history; source candidates retain access during NEEDS_INFO. Superseded unacted nominees lose nomination-only access. Actual decision/correction authors retain current-role audit access; inactive/revoked actors lose applicable access. Finance processing and service scopes remain narrow. Admin alone never grants sensitive expense/leave access. Filter before pagination and return uniform invisible/missing 404.

## Compatibility and non-goals

Additive migration performs no snapshot/decision/history backfill. Existing managed milestone 3 submissions may be captured lazily after trusted history/fields/policy/plan/decision validation. Capture records its actual actor/time and references the real original events; it does not invent original authors or dates. Inconsistent evidence blocks without writes. Unvalidated legacy records stay blocked. Downgrade refuses to discard new evidence.

No new dependencies, service clarification, frontend workflow UI, AI decisions, notifications, reversal/reopen, delegation/reassignment, analytics/SLA, AWS/deployment, actual payment or Phase 2 worker/outbox behavior.
