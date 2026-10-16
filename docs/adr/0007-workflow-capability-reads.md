# ADR 0007: Shared workflow preflight and scoped capability reads

Status: accepted within the owner's explicit Milestone 6B Phase 1 implementation
authorization. PRD v1.1 Sections 16.1 and 16.6–16.7 govern workflow/security and UI
sequencing; Milestones 3–5 remain the source of approved transition policy.

Expose additive GETs for request capabilities, creation options and enriched work
queues. Keep all existing mutation contracts. No frontend workflow buttons,
dependencies, migrations, new authorization policy or external effects are added.

`action_checks.check_action` is a side-effect-free preflight, called by capability
reads and by every new mutation inside the existing Principal validation, request
row lock, expected-version check and transaction. Exact receipt retries retain their
existing behavior. Existing authoritative helpers validate current approval steps,
snapshotted eligibility and immutable submission evidence. Lifecycle helpers now
separate reversal/reopen checks and resolution evidence inspection from persistence.
The actual mutation still validates its typed input/binding and checks domain edges
when advancing. PostgreSQL guards remain unchanged and authoritative.

Payload-free capabilities permit opening a typed form. Unknown form values are not
invented: a draft submission checks the active typed policy and current manager
readiness but cannot decide amount-dependent finance eligibility until data is
supplied. Resubmission uses its known latest proposal and checks the full current
policy/candidate plan and overlap evidence. Assignment advertises eligible choices;
the submitted user is checked again. Reasons, processing references, resolutions,
revision changes and all other typed payload validation remain mandatory.

Use repeatable-read, read-only PostgreSQL transactions for these new read models.
The returned request version and action IDs belong to one snapshot. No locks,
compatibility captures, plans, events, receipts or domain writes occur on GET.
Normal authentication session maintenance remains unchanged and separate. Time
boundaries use the database observation clock; mutations resample time after locking.
A capability is not a grant/token/reservation and can expire immediately. The UI
must match detail.version to capabilities.expected_version, refresh on mismatch or
409, and never optimistically change workflow state or replay a mutation.

Names are current display labels for already authorized request/history/current-plan
participants, not a user directory or immutable historical name snapshots. Return
only ID/name pairs, with no emails or role lists. Assignment choices exist only
when the actor can currently assign that request, and use the same department,
active-user and active-role query as mutation validation. Creation department
choices share the existing creation boundary: current active principals may choose
any existing department inside their tenant. No global user/department endpoint is
introduced. Organization timezone is explicit, validated configuration, with no
invented display fallback. Generic blockers never echo policy/candidate failures.

Work queues apply tenant/visibility predicates first and full shared checks before
effective pagination. Stream candidate rows until offset+limit+1 authorized entries
are found; do not publish totals or count hidden rows. This deliberately favors
correctness over an unsafe SQL-only approximation. A future measured performance
optimization must preserve the same preflight semantics. Current ordering is FIFO
created_at/id. Finance includes visible reversal-held expenses with a safe hold
explanation; only the process action permits actual processing. Legacy queue
endpoints remain compatible; the reversal nomination SQL predicate is shared.

Generated OpenAPI/TypeScript are the transport contract. New reads use no-store and
Vary: Cookie while preserving existing Origin variation. The established frontend
shell and its owned-read/auth adapter remain unchanged in this backend foundation
step. Extending the adapter, composing these reads and wiring typed forms/actions
are subsequent 6B work, not authorization inferred from status or roles.

The owner subsequently confirmed Phase 1 committed/pushed and CI green and
authorized Phase 2 frontend read integration. Both frontend adapters now share
the fixed read allowlist; server components compose version/evidence-matched
detail and capabilities and render disabled action availability. No mutation
adapter, new authorization rule or dependency is added. See
[the Phase 2 checkpoint](../PHASE_1_MILESTONE_6B_FRONTEND_READS.md).
