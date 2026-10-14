# ADR 0002: Phase 1 milestone 2 authentication

Accepted through explicit user approval of the design and implementation refinements.

Use PostgreSQL opaque sessions with a 256-bit random cookie token and only its SHA-256 digest persisted. Keep the existing two-ID Principal interface and requester-owned tenant predicates. Resolve the pilot organization from server configuration; current database user/role state is authoritative. No JWT, external provider or Redis session persistence.

The initial 30-minute idle/eight-hour absolute deadlines and five-minute touch interval are centrally configurable. Idle checks use persisted activity and are conservative between touches. Touch updates recheck validity and never extend absolute expiry or revive revoked/expired sessions. Multiple devices are supported; login replaces only a represented cookie session, logout revokes only the current session. Account disablement revokes all devices through a PostgreSQL trigger. Explicit credential replacement revokes all sessions transactionally; same-password Argon2 rehash is distinguished and preserves other devices.

`argon2-cffi` is the only new dependency, approved for Argon2id hashing/verification and parameter upgrades. Its initial 64 MiB/t=3/p=4 profile is configurable and benchmarkable. Password hashes remain in the existing user column. Runtime has no alternate hash implementation or test identity setting.

Use strict origin/JSON login checks and session-bound HMAC CSRF tokens for authenticated mutations. Secure HTTPS uses a host-prefixed HttpOnly/SameSite=Lax cookie without Domain; explicit loopback HTTP uses a distinct cookie name. Credentialed CORS is an exact allowlist; auth responses are not cached. Auth configuration is separate from worker settings.

Approved Redis login throttling is ephemeral abuse control only. Atomic IP/account counters use opaque identifiers and expire automatically. Client forwarding headers are ignored; Compose disables proxy-header parsing. Redis failure closes login with sanitized 503 without affecting valid PostgreSQL sessions.

Email identifiers are ASCII, canonicalized by trimming outer ASCII spaces and lowercasing; organization-scoped uniqueness uses lower(btrim(email)). Collisions block migration, never silent account merging. Request creation derives requester from Principal rather than a client field. Local initialization explicitly selects a passwordless existing account and prompts in a terminal; seeds remain unchanged.

No milestone 3, frontend auth UI, reset/invite/verification/MFA/SSO/OAuth, approvals, AI, notifications or deployment is authorized. Dependency restoration and live verification evidence remain required; see the milestone 2 results report.
