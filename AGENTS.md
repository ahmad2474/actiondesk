# ActionDesk engineering instructions

## Authority and current authorization

- Authoritative specification: `docs/ActionDesk_PRD_Technical_Architecture_v1_1.pdf`, especially Sections 16.1-16.7. Use `docs/ActionDesk_PRD_Technical_Architecture_v1.pdf` only as non-conflicting background.
- Follow explicit user instructions. Do not infer policy from incomplete PDF extraction; stop and report extraction failure.
- Phase 0 and Phase 1 milestones 1–6A, including security maintenance, are owner-confirmed complete, committed/pushed and CI green. Milestone 6B Phase 1 is explicitly authorized: backend-authoritative read-only capabilities, scoped display/choice data, enriched work queues and generated contracts. Reuse mutation authorization; keep Principal/auth/CSRF/session and existing workflow policies unchanged. No frontend mutation buttons, AI, notifications, attachments, analytics, deployment changes, commits or pushes are authorized in this step.
- `docs/PHASE_0_PLAN.md` records proposed implementation choices and open decisions. Proposals are not approved requirements. When approval arrives, update the recorded status and decisions.

## Architecture and scope

- Approved stack: Next.js with TypeScript; Python with FastAPI; PostgreSQL; Redis and durable workers; Groq primary with Gemini fallback; Docker Compose locally; eventual AWS EC2 pilot.
- Build a modular monolith with separate web, API, and worker processes. Keep domain rules independent of HTTP routers, UI, queue transport, and AI adapters. Share Python domain/services/database code between API and worker without duplicating rules.
- PostgreSQL is the source of truth. Redis transports work; it is not the authoritative business-state store.
- Pilot deploys one organization, but schema, queries, permissions, and tests must be tenant-aware from the beginning.
- Proposed repository layout follows PRD Section 8: `apps/web`, `apps/api`, `apps/worker`, `packages/contracts`, `data/seed`, `data/evaluation`, `tests`, `infra`, and `docs`.
- Phase 0: skeletons, Compose, no-op worker, migrations, CI, deterministic local seeds, baseline tests, and documentation.
- Phase 1: authentication, RBAC, manual service/expense/leave workflows, approvals, event history, and core UI.
- Phase 2: transactional outbox, durable job lifecycle, signed webhook, idempotency, recovery, and dead-letter handling.
- Phase 3: validated AI enrichment and evaluation. Durable execution must pass its exit gates before provider integration.
- Phase 4: deterministic SQL reporting, SLA scheduler, notifications, and briefing. Phase 5: privacy, attachments, backup/restore, and safety gates. Phase 6: controlled EC2 HTTPS pilot.
- No user uploads in Phases 0-4. No actual payments, payroll, email ingestion, WhatsApp integration, mobile application, visual workflow designer, arbitrary SQL agents, microservice expansion, or Kubernetes in this scope.
- Justify additional libraries/frameworks in an ADR; seek approval for scope changes or paid services. No paid services are authorized by this plan.

## Coding and API standards

- Use strict TypeScript and typed Python boundaries. Validate API input/output and AI contracts with Pydantic. Prefer small explicit functions and domain types over generic CRUD abstractions.
- FastAPI's OpenAPI schema is the API contract source. Generate TypeScript types with the approved openapi-typescript package; do not reintroduce the temporary converter or maintain independent handwritten copies. Check generated output for drift in CI.
- Version schemas and workflow policies. Keep rule definitions as typed transition tables with deterministic tests; admin settings may change bounded values, never arbitrary executable expressions.
- Route workflow state changes only through `transition_service.transition(actor, request_id, action, expected_version)`. Do not expose unrestricted status PATCH, including to admins.
- Use Decimal for monetary values and an explicit supported currency. Never use binary floating point for business money. Store timezone-aware UTC timestamps; interpret SLA calendars using configured organization timezone and business hours.
- Use SQLAlchemy models and reviewed Alembic migrations for every schema change. Do not substitute runtime `create_all` for migration history. Enforce uniqueness, foreign keys, organization consistency, and indexes in the database where appropriate.
- Keep persistence and external integrations behind explicit interfaces. Routers validate/authorize and invoke services; React components do not implement authoritative business rules.
- APIs use RFC 7807-style errors and `X-Request-ID`; document applicable 401/403/404/409/422/429 responses, pagination, and idempotency. Health endpoints disclose no secrets. Distinguish liveness from dependency readiness.
- Lock dependencies and pin container images after approval and compatibility verification. Never commit `.env` secrets, credentials, provider keys, database dumps, or sensitive logs. Provide placeholder `.env.example` values.

## Approved schema decisions

- Four roles: employee, manager, finance, admin. Users can hold multiple roles via a separate role-assignment table. Requester/assignee are object relationships; approval eligibility comes from policies and role assignments.
- Model employee-manager and department-manager relationships explicitly; versioned approval policies determine eligible approvers without hardcoded users.
- Expense approval and payment processing/completion are distinct permissions. Only authorized finance users may process/complete expenses.
- PostgreSQL owns durable workflow/job state; Celery/Redis is transport. Phase 0 worker is no-op only.

## Workflow invariants

- Check trusted authenticated identity, role, organization, object visibility, current state, required fields, and requester/approver separation before actions and before returning objects.
- Requesters cannot approve their own expense/leave, including through delegation. Admins cannot bypass this rule, invalid state edges, or immutable audit history.
- Check `expected_version` and current state inside one transaction. Conflicting writers receive 409 with authorized current-state information.
- Commit business state, immutable request event, and applicable outbox event in one PostgreSQL transaction. Preserve actor, reason, timestamps, and per-request event sequence.
- Cross-team reassignment requires manager/admin authorization and an audited reason; preserve `due_at`. Time-bounded approval delegation preserves the original chain.
- User-approved policy: cancellation only before final approval and irreversible side effects. Post-approval expense changes require an explicit authorized reversal with complete audit history, never deletion.
- Completed requests retain historical state. Reopening requires a separate authorized transition or linked follow-up, never silent state reset. Define the exact transition policy in Phase 1.
- Leave dates must be ordered; overlaps are flagged rather than automatically denied. Expense threshold examples are synthetic demo policies, not universal accounting rules.

## Durable execution contract (Phase 2)

- Use PostgreSQL transactional outbox and at-least-once Redis delivery. Never promise exactly-once queue execution or external effects.
- Persist job identity, business key, type, attempt, status, next-run time, lease, heartbeat, error class, and sanitized last error. Atomically claim jobs and recover expired leases after worker crashes.
- Before effects, check a ledger unique on `(organization_id, operation_type, business_key)`. Commit local effect receipt and state changes atomically where possible.
- External calls use downstream idempotency keys when supported; otherwise reconcile external state. Replays preserve business keys.
- Retry transient failures with bounded exponential backoff and jitter. Do not blindly retry validation/auth/permission failures. Default proposed PRD attempt limit is configurable 5; exhausted jobs require visible FAILED/DEAD_LETTER reason and explicit replay control.
- Compare aggregate sequence/version for out-of-order delivery; ignore or park stale events. Serialize effects by request when required. Reject obsolete AI results that would overwrite later manual edits.
- Signed webhooks verify HMAC over raw bytes, timestamp/replay window, stable external event ID, and deduplicate by `(organization_id, source, external_event_id)` before transactional receipt and 202 acknowledgment.
- Monitor queue age, retries, dead letters, work in progress, outbox backlog, and repeated failures. FastAPI in-process background tasks are not durable business processing.

## AI boundaries (Phase 3)

- LLMs may propose classifications, grounded extracted fields, limited clarification, and summaries. Deterministic application code owns identity, authorization, routing, approvals, state transitions, SLA rules, and side effects.
- Treat incoming text as untrusted data, never instruction granting tools or permissions. No arbitrary agent actions or model-generated SQL.
- Use provider-independent adapters. A successful HTTP response is not a valid result until schema and domain validation pass.
- Missing/conflicting critical values remain null and require clarification. Preserve evidence spans or explicit sources. Never invent expense amount/vendor or leave dates.
- Use short timeouts, bounded transient retries, temporary circuit breaking, one bounded fallback attempt, per-request call budgets, and global quotas. Both-provider failure leaves manual workflows usable.
- Summaries/briefings use only authorized supplied facts and cite request IDs. Briefing facts and metrics come from SQL; provider failure returns a deterministic list.
- Record prompt/model/schema versions, latency, validation status, fallback, token/cost estimates, and sanitized errors; ordinary telemetry excludes prompts and personal content.
- Verify provider quotas and data terms at integration time. Restricted HR/financial data cannot go to free endpoints without permitted terms and organizational consent/contractual controls.

## Security, privacy, and operations

- Deny access by default. Scope every business query to organization and enforce finer financial/leave visibility across requests, comments, history, summaries, exports, and later attachments. Test ID enumeration and indirect access.
- Password auth uses Argon2id or bcrypt; production pilot requires reviewed secure login or OIDC. Cookie auth uses HttpOnly/SameSite, Secure under HTTPS, and CSRF protection. Rate-limit login and public ingress.
- Secrets remain server-side in environment/IAM-managed configuration. Use scoped IAM, key rotation, and a secret-access runbook. Do not put secrets in browser bundles or public demo credentials.
- Use synthetic data only for the initial demo. Redact bodies, tokens, employee details, invoices, and provider responses from ordinary logs.
- Retention values such as 90-day raw text, 30-day debug metadata, and 12-month events are proposals requiring review, not immutable policy. Document deletion/export, backup behavior, and audit/financial retention exceptions.
- Before external onboarding: privacy notice, terms/consent, provider data-handling review, restore test, deletion rehearsal, and incident contact procedure.
- Eventual EC2 runs behind HTTPS with restricted security groups and no public PostgreSQL/Redis ports. Nightly off-host encrypted backups and tested restore are minimum pilot requirements. Include image scanning, updates, disk/5xx/queue/budget alerts.
- Phase 5 attachments use private S3, authorized short-lived access, random keys, MIME/signature checks, malware scan or quarantine, retention cleanup, and audited metadata. Initial configurable limits: 10 MB/file, 5 files/request, PDF/JPEG/PNG only. No automatic model upload; require authorized opt-in and sensitive-data screening.

## Tests and completion evidence

- Run applicable lint, formatting, Python/TypeScript type checks, unit and integration tests, migration checks, and contract drift checks. Use real PostgreSQL/Redis for tests of their transaction and recovery semantics.
- Phase 0 exit: repeatable one-command local startup and green baseline tests. Verify migration from empty DB, deterministic repeatable seeds, health/readiness, placeholder web, and no-op worker. CI mirrors documented checks and requires no AI keys.
- Phase 1: all three manual happy paths and reject/needs-info paths; self-approval, cross-org/role/IDOR, invalid transitions, concurrent conflicts, atomic event persistence, Decimal boundaries, and date rules.
- Phase 2: duplicate webhook/delivery, worker death and lease recovery, outbox publish crash windows, bounded retry, dead-letter replay, and out-of-order effects.
- Phase 3: frozen human-reviewed held-out set of at least 300 cases; at least 30 each missing-field, Roman Urdu/code-switching, conflicting-fact, and injection/adversarial cases (overlap allowed). Keep evaluation separate from prompt/demo examples.
- AI gates: >=95% type accuracy, >=95% explicitly stated required-field exactness scored per field, >=95% missing-info recall, zero fabricated critical fields, zero cross-role/tenant leaks, 100% malformed-output rejection or safe normalization, and 100% deterministic creation/approval tests passing with both providers disabled. Record per-class metrics, failure categories, and p50/p95 latency/fallback/token/cost telemetry.
- If AI performance misses provisional quality targets, require human review; never relax critical-field safety. Use deterministic assertions, not LLM judges, for business invariants.
- Test accessible responsive journeys and empty/loading/error/offline/AI-unavailable states when UI exists. Pilot additionally requires upload gates, backup/restore and deletion rehearsals, security review, and real tester feedback.
- Report exactly what was checked and what remains unverified. Do not claim deployment, adoption, AI accuracy, or passed gates without evidence. Avoid tests that merely mirror implementation.

## Working practice

- Before changing code, identify the authorized phase and relevant PRD sections. Record unresolved policy questions rather than inventing rules.
- Keep changes focused, reviewable, and accompanied by relevant documentation and validation. Do not broaden scope or install speculative future dependencies.
- Stop at Milestone 6B Phase 1 read-model foundation. Further workflow UI wiring requires a subsequent review checkpoint. Report actual validation evidence and deviations before declaring completion.

## Approved milestone 3 policy

- Service cancellation stops before work starts; assigned cancellation requires department manager/admin review. Milestone 5 supersedes terminal leave approval and deferred reversal/reopen only within its approved boundaries below. Service clarification, delegation and reassignment remain deferred. Expense/leave correction follows the milestone 4 decisions below.
- Every expense requires manager approval, with finance approval strictly above an explicitly configured policy threshold. No universal numeric threshold or default active policy is selected.
- Prefer a valid explicit employee manager; department fallback requires policy permission. Multiple eligible managers are one-of candidates. Missing candidates block submission without partial writes.
- Snapshot candidates at submission and recheck current role, active user, tenant and recorded relationship at decision time. Never silently substitute candidates. Admin alone cannot approve expense/leave.
- A non-requester holding the required roles may separately perform manager approval, finance approval and processing. Each creates separate durable evidence. Requester self-approval/processing remains forbidden.
- Submitted authoritative expense/leave fields and policy/plan evidence are frozen. Participant scopes apply to detail/history, actionable approvals and service/finance work queues; admin has no blanket sensitive-content visibility.
- Legacy nominees/history are preserved. Read-only explicit assessment reports missing evidence; unvalidated historical records cannot enter live approval/processing paths.


## Approved milestone 4 policy

- Expense and leave only. Current actionable snapshotted candidates alone may request changes, subject to current tenant, active-user, role and recorded relationship checks; requester self-review and admin-only authority remain forbidden.
- NEEDS_INFO suspends review. Pending steps close as cancelled linked to immutable correction evidence, distinct from rejection/withdrawal. Existing decisions remain historical only. Owners may withdraw while NEEDS_INFO.
- Only the requester revises/resubmits. Complete typed snapshots use expense vendor/amount/currency/purpose or leave dates/type, plus bounded clarification. Original raw_text stays immutable; no arbitrary patches.
- Proposed snapshots stay separate from the submitted projection. request_revisions, request_submissions and request_change_requests are append-only. Each revision has a same-state event and one version increment.
- Resubmission requires the latest proposal from the current correction cycle, selects the active immutable policy and resolves fresh current candidates. Every resubmission requires full manager/optional-finance reapproval, including explanation-only changes. Missing policy/candidates returns 409 with no partial writes.
- All approval ordering, queues, decisions and processing/completion checks scope to the current submission sequence. Historical steps/candidates never satisfy a new plan.
- Superseded unacted candidates lose nomination-only visibility; actual decision/correction authors retain only active-role audit visibility. No blanket sensitive-content admin scope.
- Additive migration preserves original evidence. Lazy capture of managed milestone 3 submissions requires consistent existing trusted evidence, records the actual capture actor/time and never fabricates historical facts. Unvalidated legacy records stay blocked.
- Exact retries preserve the original outcome without duplicate snapshots, plans, closures or events; current authentication/visibility still apply. No commit or next milestone is authorized.


## Approved milestone 5 policy

- Expense APPROVED and unprocessed may enter REVERSAL_REVIEW; COMPLETED is terminal. Leave reversal initiation and acceptance require a date strictly before start_date in the current organization timezone. No retrospective reversal.
- Requester or a currently eligible candidate from the final required step of the current approved submission may initiate reversal. Only an independent currently eligible final-step candidate may accept or deny: neither requester nor initiator may decide. Missing independent candidates leave review blocked. Admin/processing roles alone confer no reversal authority.
- REVERSAL_REVIEW blocks processing. Acceptance makes the source REVERSED terminal; denial restores the same APPROVED authorization without another approval or changed approved_at. All original approvals remain immutable.
- Only the requester may create one new linked correction DRAFT after an accepted correct-intent reversal. Copy organization, owner, type, department, title, original raw intake and due_at. New request/submission/approval identities and current-policy fresh review are required; no old approval is reused.
- RESOLVED service requests may reopen to REOPENED under explicit immutable/versioned organization policy, then start a new IN_PROGRESS cycle. CLOSED remains terminal. Requester, current department manager or admin may reopen; preserve valid active same-department assignee, assignment and due_at. Every cycle needs its own immutable resolution before closure.
- Approved pilot reopening window is explicit configuration of 604800 seconds (7 days), inclusive from the latest actual resolution. Valid range is 3600–2592000 seconds. No absent/invalid-policy application default. Evaluate time after locking; database guards additionally prevent backdated expiry/date bypass.
- Reversal requests/decisions, correction links, service resolutions/reopenings and policy versions are append-only and tenant-qualified. Current pointers require matching transition evidence. Lazy compatibility capture requires sufficient existing trusted evidence; no fabricated history/backfill. Legacy unvalidated records remain blocked. Downgrade refuses evidence loss.
- Existing Principal, sessions, CSRF, tenant/version/idempotency architecture remains unchanged. Exact retries return durable original outcomes and current authorized detail without duplicating effects or changing later state.
- No refunds, financial adjustments, payroll/calendar undo, completed-expense correction, closed-service reopen, delegation/reassignment, service clarification, AI, notifications, frontend UI, analytics/SLA, deployment, Phase 2 work, commits or pushes are authorized.


## Approved milestone 6A UI boundary

- Warm-neutral/deep-teal, light mode, system sans, custom CSS tokens and scoped components. No full UI/state/form framework or branding project.
- Unified role-union navigation is orientation only. Real login/me/logout and read-only owned-request/detail/evidence use unchanged backend Principal/session/CSRF rules. Never infer workflow authorization from roles/status/candidates. No optimistic state changes or automatic mutation retry.
- Same-origin adapter uses a fixed server-only upstream and allowlisted auth/read paths; it exposes no request creation or transition mutation. Preserve HttpOnly/Origin/CSRF, no-store reads, and memory-only CSRF. No sensitive browser storage.
- Workflow/create/revision/queue/action states are clearly isolated fictional previews, never blended into live API responses. No active-action capability or directory API is added; those require milestone 6B approval.
- Approved dependencies: selected Radix dialog/alert-dialog/dropdown/tabs primitives, Lucide, and axe Playwright. No Themes, shadcn, Tailwind, React Query, Zustand, form library or Storybook. Record locks/justification in ADR 0006.
- Verify desktop/laptop/tablet/mobile through 320px, long evidence, role unions, keyboard/focus/dialogs, contrast, reduced motion, session expiry, HTTP/network errors and screenshot consistency. Browser authentication checks use a disposable test database/account, never development credentials. Report any manual screen-reader or platform baseline limits honestly.


## Approved milestone 6B Phase 1 boundary

- Read-only request capabilities and queues derive authority from the same shared preflight as locked mutations, never frontend roles/status. Bind actions to request version/current evidence IDs; mutations always revalidate.
- Display names/choices stay tenant- and participant-scoped. No global user directory, hidden candidate/policy disclosure or admin-only sensitive-content access.
- Read models do not write or lazily capture business evidence. Preserve immutable approvals, revision/correction, reversal, service-cycle, idempotency and database invariants.
- No UI redesign, mutation-button wiring, dependencies, migrations, AI, notifications, uploads, analytics, deployment, commit or push. See docs/adr/0007-workflow-capability-reads.md and docs/PHASE_1_MILESTONE_6B_READ_MODELS.md.
