# Phase 0 tenant-integrity review

Status: source review complete; PostgreSQL enforcement tests are written but blocked by unavailable backend dependencies and Docker access. This is not a claim of verified authorization.

## Relationships

The foundation uses globally unique UUID primary keys plus organization-qualified foreign keys for business relationships. Referencing a UUID alone does not grant access.

| Relationship | Tenant constraint |
| --- | --- |
| User to department | `(organization_id, department_id)` references department organization/ID |
| Role assignment to user | `(organization_id, user_id)` references user organization/ID |
| Employee/department manager | Same-organization user and manager-role assignment; department reference is also organization-qualified |
| Request creator, assignee, department, policy and follow-up | Every reference includes the request's organization |
| Request processor | Organization/user/role reference, paired nullable actor/role fields, and finance-only role check |
| Request fields and events | Organization/request reference; nullable event actor is organization-qualified when present |
| Approval | Organization/request/requester reference plus same-organization role-qualified approver; requester separation check |
| Outbox | Organization/request reference and organization/business-key uniqueness |

Optional references may be null; populated references must match their owning organization. System events may have a null actor. Roles can be revoked without removing historical role-qualified references; the presence of a role-assignment row alone does not prove current eligibility.

Uniqueness covers organization slug, organization/email, department names per organization, role assignment triples, employee-manager assignment, department-manager triples, policy name/version per organization, request event sequences, approval steps, and outbox business keys. Indexes support tenant/status/time, tenant/assignee/status, tenant/due date, approval queues, and outbox dispatch scanning.

`tests/integration/test_database.py` now compares deployed tables, columns, foreign keys, uniqueness and indexes against model metadata, and exercises 16 cross-organization relationship cases. FK failures must have PostgreSQL SQLSTATE `23503`; unrelated SQL errors cannot satisfy the tests. These tests have not executed in the current environment.

## Query and authorization boundaries for Phase 1

- Authenticated server identity must provide organization and active roles. Never derive trusted organization from request JSON, URL IDs, generated fields, or LLM output.
- All business reads/writes must include organization predicates and object visibility. ID-only lookup is insufficient. Apply finer requester/assignee/eligible-approver rules to financial/leave data, comments, event history, exports and summaries.
- Resolve approval eligibility through versioned policies and current manager relationships. Check role revocation, delegates, requester separation and object state in application code. Composite foreign keys prevent malformed relationships but do not authorize actions.
- Treat organization ownership as immutable for business objects. Admin role does not bypass tenant visibility, audit immutability, invalid transitions, or self-approval prohibitions.
- Workflow mutations must pass the transition service, expected-version check, permissions and one-transaction state/event/outbox boundary. There are no such endpoints in Phase 0.
- Health/readiness queries are limited operational exceptions: dependency probes and the Alembic revision table. They return no business objects.
- PostgreSQL row-level security is not implemented in Phase 0. Query/object authorization and regression tests remain mandatory before Phase 1 can be accepted; database constraints are not a replacement.
- Seed helpers are local synthetic fixture operations, not request-serving repositories or an authorization service. Integration tests create their own database; they do not downgrade or reset the development database.

No tenant-routing middleware, business APIs, or Phase 1 authorization features were introduced in this review.
