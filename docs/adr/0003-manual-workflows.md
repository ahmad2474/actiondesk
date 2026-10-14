# ADR 0003: deterministic manual transitions and immutable approval evidence

Status: accepted for Phase 1 milestone 3 by explicit project-owner authorization. No new library, infrastructure, transport behavior or paid service is introduced.

Use the pure typed forward transition table in `app.domain.workflow` and one transactional `transition_service.transition` entry point. The authenticated Principal remains the sole trusted actor/tenant source. PostgreSQL row locks serialize request versions; an actor/tenant/key advisory lock also serializes idempotency keys reused across different requests. Receipts bind request, action and canonical payload hash, recording only the outcome version/status and optional decision ID. Retry responses pair this historical compact outcome with currently authorized detail rather than persisting sensitive response bodies.

A selected immutable policy version and immutable approval candidate snapshots explain routing. Mandatory manager approval precedes optional finance approval strictly above an explicitly configured threshold. No default threshold is inferred from seed examples. Explicit employee-manager relationships take precedence; policy-authorized department fallback yields one-of candidates. Decision-time roles, active user, tenant membership and recorded relationship are rechecked under locks. No silent substitutions are made.

`approvals` remains a step projection. A separate append-only actual-actor decision links each acted step to the matching immutable request event. Rejection/withdrawal closes unacted steps through audited cancellation without fabricating decisions. Expense approval and finance processing are separate actions/evidence; requester separation holds even for multiple roles/admin. Submitted authoritative fields, policy references, snapshots and completion attribution are frozen by database guards as well as service validation.

Participants have narrowly scoped reads. Administrators can route/close service requests but receive no sensitive expense/leave visibility merely from the admin role. Approval and work queues filter authorization in SQL before pagination.

Legacy nominees, policies and history are preserved without backfill. A read-only explicit assessment reports missing provenance, plan and candidate/decision evidence. Historical approval mutations remain blocked; this milestone introduces no repair/activation mechanism that invents historical facts. Downgrade refuses to discard live workflow evidence.

The scope deliberately excludes revision/NEEDS_INFO, reversal/reopen, delegation/reassignment, workflow UI, notifications, AI decisions and durable execution. There are no external effects requiring an outbox event in this milestone. Durable jobs and outbox transport remain Phase 2 work.
