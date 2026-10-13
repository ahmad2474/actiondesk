# ActionDesk Phase 0 implementation plan

Status: Phase 0 authorized on 14 October 2026 with the user decisions in `docs/adr/0001-foundation.md`. This document retains the original proposal for traceability; the ADR and user instructions override unresolved recommendations below. Verification status is recorded in `docs/PHASE_0_RESULTS.md`.

## Evidence and interpretation

Read both PDFs in full using text extraction; inspected rendered roadmap and release-gate pages to verify table interpretation. V1 has 8 pages; v1.1 has 12. The v1.1 title and revision establish authority even though its footers still say v1.0.

Repository inspection found only the two PDFs and `.DS_Store`. There is no Git repository, application code, dependency manifest, CI, Compose configuration, or existing AGENTS.md.

Source of truth: `ActionDesk_PRD_Technical_Architecture_v1_1.pdf`, Sections 7-14 and 16.1-16.7. V1 provides background only. V1's Phase 2 AI / Phase 3 durable async ordering is superseded by v1.1: durable execution in Phase 2, AI in Phase 3. V1.1 also forbids uploads in Phases 0-4 and adds job recovery, privacy, and measurable AI gates.

The retained Section 15 checklist includes login and request APIs, while Sections 16.6-16.7 place those in Phase 1. Proposed interpretation: Phase 0 stops at the foundation, schema, fixtures, and baseline policy tests; no login, request CRUD, approval actions, or workflow screens. A no-op worker in Phase 0 establishes the process boundary, not a claim of durable job completion.

## Requirements and acceptance criteria

The PRD's Phase 0 exit criterion is repeatable one-command startup and green baseline tests. The following translates that into proposed reviewable evidence:

| Deliverable | Acceptance evidence |
| --- | --- |
| Monorepo and decisions | Documented component boundaries, approved tooling, phase scope, and unresolved policy decisions; source PDFs preserved |
| Local environment | After documented prerequisites/local environment setup, `make dev` builds and starts web, API, PostgreSQL, Redis, and no-op worker from a fresh checkout |
| Repeatability | Empty database migrates to head before seed/run; restart preserves data; migration and seed reruns succeed without duplicate fixtures |
| Skeleton services | Placeholder web loads; `/health` checks liveness; `/ready` reflects database/Redis and migration readiness with sanitized output; worker boots and shuts down cleanly with no business jobs/provider calls |
| Database | Reviewed Alembic migrations for organizations, users, requests, request_events, approvals, outbox, and supporting core relationships; tenant consistency, event sequencing, and version fields checked |
| Local seeds | One fictional organization, local role fixtures, and 100 deterministic requests covering service/expense/leave; internally consistent fields/events/approvals; no real data or public shared credentials |
| Typed boundaries | Typed FastAPI schemas, OpenAPI export, generated TypeScript contract types, and automated drift check for implemented skeleton endpoints |
| Baseline verification | Format/lint/type checks, health/readiness tests, migrations and seed integration checks, web smoke, worker lifecycle smoke, and small deterministic policy tests all green |
| CI and documentation | GitHub Actions definition runs baseline checks without AI keys; README gives prerequisites and approximately 10-minute run instructions excluding first image downloads, plus architecture diagram and commands |

The 100-request seed follows v1.1 Section 14. Section 15 also describes a 10-request first milestone; recommend a 10-request minimal fixture subset and 100-request default. The later 2,800-request corpus and 300-case AI evaluation set are not Phase 0 deliverables.

Proposed policy tests in Phase 0 cover agreed pure predicates such as Decimal threshold boundaries, date order, and explicit no-self-approval. The complete transition engine, role enforcement, and end-to-end workflows belong to Phase 1. Do not implement rules whose semantics remain unresolved.

## Proposed monorepo

```text
ActionDesk/
  AGENTS.md
  README.md
  Makefile
  .env.example
  .gitignore
  pyproject.toml                 # backend package + approved dev tooling
  uv.lock
  package.json                  # npm workspaces for web/contracts
  package-lock.json
  apps/
    web/                        # Next.js App Router, strict TS, UI, API client
    api/
      app/
        api/                    # routers and auth dependencies
        core/                   # typed settings, logging, health configuration
        domain/                 # pure rules, permissions, versioned policies
        services/               # use cases and transaction boundaries
        integrations/           # later provider/webhook/notification adapters
        db/                     # SQLAlchemy models, scoped repositories
      migrations/               # Alembic revision history
    worker/                     # separate entrypoint; same Python package/image
  packages/contracts/           # generated OpenAPI TS types, no business rules
  data/
    seed/                       # canonical synthetic fixtures
    evaluation/                 # reserved; held-out corpus added in Phase 3
  tests/                        # unit, integration, auth, reliability, e2e
  infra/
    compose.yaml
    docker/                     # web/backend Dockerfiles
  docs/
    [existing PRD PDFs]
    PHASE_0_PLAN.md
    adr/
  .github/workflows/ci.yml
```

This is a target layout; populate directories only when needed. API and worker use one installable Python package with explicit entrypoints, avoiding path hacks and duplicated domain code. Generated contracts come from FastAPI OpenAPI. The web calls authoritative FastAPI services; Next.js does not duplicate authorization or transitions.

Compose initially has five required services. A one-shot migration/seed setup task can establish ordering. Mount development code for reload, use persistent local volumes, keep PostgreSQL/Redis internal by default, and bind exposed development ports to localhost. Reverse proxy, scheduler, EC2 bootstrap, and backup scripts arrive in their relevant phases.

## Proposed dependency choices

These are proposals, not installations or approved version pins. Select maintained compatible versions and commit lockfiles during approved implementation.

| Area | Proposed choice | Reason / timing |
| --- | --- | --- |
| Frontend | Next.js App Router, React, TypeScript; npm workspaces | Approved frontend; simple workspace management without another monorepo framework |
| Backend | FastAPI, Uvicorn, Pydantic, pydantic-settings | Typed REST, server process, validated DTOs/configuration |
| Persistence | SQLAlchemy 2-style models, Alembic, Psycopg | Explicit transaction control, reviewed migrations, PostgreSQL driver |
| Redis access | redis-py | Local readiness and later broker support; Redis remains transport |
| Python packaging | uv with pyproject.toml and uv.lock | Reproducible shared API/worker dependency set; requires tooling approval |
| API types | openapi-typescript plus native fetch | Generate TS types without adding a client runtime or second schema source |
| Python checks | pytest, HTTPX, Ruff, mypy | Meaningful API/integration tests, formatting/lint, Python typing |
| Web checks | TypeScript compiler, ESLint, Prettier; Playwright smoke | Static checks and actual rendered skeleton verification; full journey tests in Phase 1 |
| Automation | Make, Docker Compose, GitHub Actions | Matches PRD command and CI expectations |
| Durable workers | Recommend Celery with Redis in Phase 2, pending ADR | Existing worker transport reduces bespoke queue machinery; PRD lease/job/effect guarantees still require explicit PostgreSQL design |
| Auth / AI | Select auth hashing/session libraries in Phase 1; provider SDKs/HTTP adapters in Phase 3 | Avoid installing unused future integrations |

Official references checked while planning: [Next.js App Router](https://nextjs.org/docs/app), [FastAPI OpenAPI client generation](https://fastapi.tiangolo.com/advanced/generate-clients/), [Alembic](https://alembic.sqlalchemy.org/en/latest/), and [Celery Redis transport](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html). Celery's Redis visibility timeout permits redelivery; it does not by itself satisfy the PRD's durable leases, effect ledger, replay, or ordering guarantees. PostgreSQL job records and outbox reconciliation must be designed and tested in Phase 2 regardless of transport.

No additional hosted/paid service, LLM orchestration framework, frontend state framework, UI framework, or monorepo build framework is proposed. AWS deployment and Phase 5 S3 use remain future work, with costs reviewed before provisioning.

## Implementation sequence and checklist

Phase 0 is authorized. Source implementation is present; the checklist below remains the exit-work checklist until all runtime checks pass. See `PHASE_0_RESULTS.md` for actual completed checks and blockers.

- [ ] Confirm Phase 0 scope, seed interpretation, and tooling decisions; record ADRs and update proposal status.
- [ ] Initialize local Git repository and create root manifests, ignore rules, lockfiles, README, Makefile, and CI skeleton. Remote repository creation/connection is a separate decision.
- [ ] Create web placeholder and API skeleton with typed settings, sanitized logs/request IDs, health/readiness, OpenAPI, and no business endpoints.
- [ ] Add PostgreSQL/Redis Compose services, persistent volumes, backend/web images, and no-op worker sharing the backend package.
- [ ] Add migration and startup ordering; fail clearly on missing configuration or failed migrations.
- [ ] Design core schema, organization-consistent relationships, enums, versions, unique event sequencing, approval constraints, outbox indexes, and immutable-history access approach.
- [ ] Write and review initial Alembic revisions. Include supporting membership/team/request-field tables where core fixtures require them; defer jobs/effect-ledger and non-foundation tables to later reviewed migrations.
- [ ] Add deterministic synthetic seed loader with stable IDs and explicit local-only credentials, 10-request minimal subset, and default 100 requests. Verify reruns.
- [ ] Add small agreed policy predicates and tests without wiring workflow APIs; record unresolved manager/cancellation semantics.
- [ ] Export OpenAPI and generate TS types. Add contract drift, Python/TS lint/type, migration/seed, service readiness, worker lifecycle, and browser smoke checks.
- [ ] Complete GitHub Actions definition; run equivalent checks locally. Hosted CI execution can only be evidenced once a remote repository exists.
- [ ] Verify documented `make dev`, `make test`, `make lint`, `make typecheck`, and `make contracts` from a clean local environment. Document explicit destructive reset separately.
- [ ] Review exit evidence and known limitations with the user before Phase 1.

After Phase 0: Phase 1 builds manual workflows; Phase 2 proves durable processing; Phase 3 adds AI; Phase 4 operations; Phase 5 safety/attachments; Phase 6 pilot. Security and permission correctness begin with the first relevant feature rather than waiting for Phase 5.

## Decisions requiring approval or clarification

| Decision | Recommendation | Needed by |
| --- | --- | --- |
| Phase boundary | Approved: no-op worker now, auth/full workflows Phase 1, durable machinery Phase 2 | Resolved |
| Seed count | Approved: 100 synthetic requests plus additive 10-request subset | Resolved |
| Tooling | Approved: npm workspaces, uv, SQLAlchemy/Alembic/Psycopg, openapi-typescript contracts and checks; dependency installation/locking pending | Approved; deviation documented |
| Worker library | Provisionally approved Celery/Redis; Phase 0 is no-op only | Detailed durable design Phase 2 |
| Git/CI remote | Local Git approved but sandbox denied initialization; no remote creation/push authorized | Environment access; remote deferred |
| Roles and reporting hierarchy | Approved four roles and multi-role assignments; explicit employee/department managers and policy-based eligibility | Resolved schema; confidentiality/delegation Phase 1 |
| Workflow edge cases | Approved cancellation before final approval/irreversible effects; authorized audited reversal afterward; historical completion retained; finance-only processing | Remaining state edges and policy defaults Phase 1 |
| Organization defaults | Propose Asia/Karachi and PKR for synthetic examples; business hours, holidays, SLA thresholds, urgency rules remain configurable and require confirmation | Fixtures now; SLA implementation Phase 4 |
| Authentication | Recommend local Argon2id credentials and same-origin cookie sessions with CSRF defenses; choose reviewed pilot auth/OIDC before external users | Phase 1 / pre-pilot |
| Provider/privacy/operations | Choose models, budgets, data terms, AWS region, retention, email channel, backup destination, and pilot cost ceiling later; no assumed numeric defaults | Respective phases, before real data/onboarding |

The user resolved role cardinality: a separate role-assignment table supports multiple roles. The approved cancellation/reversal/reopening safety constraints are recorded in ADR 0001 and foundation predicates/schema. Full state edges remain Phase 1; no engine or action endpoint is implemented.

## Proposed AGENTS.md and current completion

Root `AGENTS.md` captures specification precedence, approved stack, phase constraints, deterministic workflow/security ownership, typed APIs/migrations, durable-job semantics, privacy/attachments, testing gates, and the current approval hold. Approved choices and domain refinements are recorded in ADR 0001; current deviations are in the results report.

The initial planning turn created this plan and AGENTS.md without implementation. The subsequent authorized Phase 0 turn added foundation source and ran the available checks. Runtime acceptance is incomplete: see PHASE_0_RESULTS.md. No Phase 1 features, external AI, AWS, remote Git writes, or real customer data were introduced.
