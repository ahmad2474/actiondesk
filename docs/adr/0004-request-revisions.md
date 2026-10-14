# ADR 0004: immutable request revisions and full reapproval

Status: accepted by explicit owner approval for Phase 1 milestone 4.

Expense/leave correction follows request_changes → NEEDS_INFO → revise → resubmit → SUBMITTED → MANAGER_REVIEW through the existing transactional transition service. Only a currently eligible recorded candidate for the actionable step can request changes. Only the requester revises/resubmits. The authenticated Principal and existing session/CSRF architecture remain unchanged.

Store append-only revision, submission and change-request evidence. Keep proposals separate from submitted projections until resubmission. Preserve original intake, old policies/candidates/decisions and existing history. Close pending steps with correction-linked cancellation; never fabricate rejection decisions. Select the active policy and create a completely fresh candidate plan on resubmission. Full reapproval, including explanation-only changes, avoids fragile field-specific approval carryover rules.

Scope every approval ordering, queue, decision and processing/completion check to the current submission sequence. Null step submission sequences denote the immutable original milestone 3 plan; explicit sequences identify new plans. Actual decision/correction authors retain current-role audit access, while superseded unacted nominees lose nomination-only visibility.

Existing managed submissions are captured lazily only after their trusted evidence validates. Capture records actual observation actor/time and references real original history. Legacy records are not activated or repaired. Database guards enforce evidence/projection matching and immutable records; the Principal remains the actor authority that SQL cannot independently authenticate.

No dependency, authentication, Redis/Celery, external-effect, UI or deployment change is required. Delegation/reassignment, service clarification, terminal reversal/reopen and later milestones remain deferred.
