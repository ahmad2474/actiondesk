# Phase 1 Milestone 6A: Application shell and read-only workspace

Final owner-requested [visual polish](PHASE_1_MILESTONE_6A_POLISH.md) records the smaller Home hero, mobile hit areas, accessible full-ID inspection/copy, evidence grouping and expanded dialog screenshots. It retains the approved design and all security fixes.

Security follow-up: [login native-fallback credential leak](PHASE_1_MILESTONE_6A_LOGIN_SECURITY.md) records the blocker, fix, credential rotation and new regression coverage. The original verification below did not cover submission without hydration.

Scope: explicit owner-approved 6A implementation. Milestones 1–5 are owner-confirmed complete, pushed and CI green. This milestone is local and uncommitted. No commit/push, deployment or Milestone 6B work was performed.

Owner-selected local login identifiers now use `@actiondesk.ahmad` throughout seeds, previews, test accounts and account instructions. The four existing synthetic local accounts were renamed in one guarded transaction; passwords, sessions, roles and all 100 request ownership links were preserved. Stable seed UUIDs retain their historical namespace. This is a local identifier change, not DNS/email hosting. Normal seeds remain additive; existing rows on other checkouts are not silently renamed by bootstrap.

Domain-change verification: **34 auth/request unit tests**, **8 live PostgreSQL/Redis auth tests**, and **12 desktop real-auth/security browser tests** passed. Production build, ESLint, TypeScript, Ruff lint/format (83 files), and `git diff --check` passed. Two mixed-case collision fixtures initially retained the former suffix; after updating them, all 8 live auth tests passed (11.41s). The browser run passed in 18.5s. The prior full five-viewport security verification is recorded separately below; it was not repeated for this identifier-only follow-up.

## Delivered experience

Custom warm-neutral/deep-teal light design, system sans typography, CSS tokens and root-scoped CSS Module components. Restrained wordmark, semantic status treatments, compact desktop tables/mobile cards, responsive sidebar/drawer, account menu and clear page hierarchy. No gradients, generic theme, notification placeholders, search, role switcher, fake totals, unsupported filters or analytics.

Live surfaces:

- `/login`: existing real email/password authentication, visibility toggle, errors, throttling feedback and session-expiry explanation.
- `/`: greeting, latest five owned requests and role-union workspace links; no inferred organization metrics.
- `/requests`: real owned records, fixed backend ordering, limit/offset pagination and no invented total.
- `/requests/{id}`: read-only owned detail, authoritative current values, current workflow/status, approval evidence, paged revision/submission/change-request evidence, reversal/correction links, service cycles and immutable event history.
- Account menu: real current identity/roles and CSRF-protected logout.

Approvals, Service Work, Finance Processing and New Request are live shell destinations that explicitly explain their preview-only scope. They do not display fictional queues as real work. `/preview` is a separate public fictional workspace with a persistent banner, fictional accounts and no business mutations. It demonstrates approval/reversal queues and dialogs, service triage/assignment/start/resolve forms, finance processing/reference forms, service/expense/leave creation, frozen submitted/proposed correction values, revision forms, accepted reversal/correction links, multiple service cycles, long titles/reasons/history and loading/empty/error/conflict states.

Current submission values and proposal values stay separate in both real reads and examples. Earlier approvals are visibly historical, and pending candidates are not shown as decision authors. Reasons are preserved as plain text with line breaks, actor IDs remain available, and event timestamps are shown explicitly in UTC. No missing legacy decisions/snapshots are fabricated. Evidence pages report their offset and expose previous/more controls independently from the complete request event timeline.

## Security/data boundary

Generated OpenAPI contracts remain the transport source. Server Components compose read-heavy pages; client components handle auth, responsive navigation, dialogs and fictional forms. Money grouping uses BigInt from decimal strings, never floating-point business arithmetic. Leave dates stay date-only. No backend models, migrations, policies or workflow routes were changed.

Server-only ACTIONDESK_API_URL is a fixed validated HTTP(S) upstream. Compose explicitly supplies http://api:8000; direct development defaults to http://127.0.0.1:8000. The same-origin `/api/actiondesk` adapter forwards only login/logout POST and allowlisted authenticated reads. Lists always use mine scope. It never forwards request creation/transition POST or trusted identity claims. Cookies, actual browser Origin, CSRF, Set-Cookie, request IDs and Retry-After are preserved; authenticated reads are no-store and pages dynamic. Existing FastAPI Principal/tenant/object/session/CSRF checks remain authoritative. Live detail composition additionally restricts ownership for this release.

CSRF is obtained through current session context and retained only in memory. No sensitive session/form data is written to local/session storage. There are no optimistic workflow changes or automatic mutation retries. Restored pages verify the session; expiry removes sensitive content. Account/organization/role changes force a fresh navigation so old owned content is not reused across identities. Logout uses current session CSRF and clears navigation through a full sign-in return.

## Responsive and accessibility checks

Viewport projects: 1440×1000 desktop, 1280×720 laptop, 768×1024 tablet, 390×844 mobile and 320×740 narrow. Sidebar switches to a keyboard-accessible drawer below 1024px; tables become cards below 768px; summary is followed immediately by workflow state on constrained layouts. Workflow panel is sticky only at width ≥1280px and height ≥850px, otherwise normal flow.

WCAG 2.2 AA is the target. Axe scans cover representative pages/login and dialog states. Keyboard scripts verify skip link, drawer/menu focus, dialog containment/Escape/restore, alert-dialog cancel focus and state announcements. Descriptive per-page browser titles, semantic headings/landmarks/tables/forms, visible labels, error association, non-color status text and reduced-motion rules are present. Desktop/mobile and long-content screenshots were visually inspected; that review caught and corrected overlapping synthetic shortcut labels. It also caught and corrected fixture consistency: NEEDS_INFO shows the original submitted amount separately from a new proposal, and current approved-submission step evidence matches its approvals.

Measured token contrast: primary text/white 14.52:1; secondary text/white 5.61:1 and canvas 5.21:1; teal/white 7.06:1; semantic success/warning/error/info pairs 6.44/6.21/6.17/6.87:1; control outline/white 3.25:1. These measurements complement, rather than replace, the rendered axe checks.

## Reproducible validation

`make test-web` now runs scripts/test_web.py: production build, a loopback-only API on 8010 backed by a generated actiondesk_test_browser_* PostgreSQL database, loopback production Next server on 3100, five Playwright projects, and cleanup of only its own processes/container/database. Use unused ports and running Compose PostgreSQL/Redis. COMPOSE_FILES selection works with local/base images. Test-only credentials/fault/expiry routes exist only in tests/browser/serve.py, never runtime. Credentials and the fixture auth secret are generated in memory; no passwords are printed. Fixture login limits are raised for throughput while the original backend integration suite verifies real limiter semantics.

Real browser tests cover HTTP-only cookies, auth redirects, owned list/detail/evidence/pagination, actual CSRF rejection/logout, expiry, account switching, no browser storage, no UI workflow writes, adapter rejection of transition POST, login validation/visibility, controlled 403/422/429/network failures and real request 404/403/409/422/503 presentation. No production identity override or development-account initialization is used.

Final local results:

| Command/check | Result |
| --- | --- |
| `.venv/bin/ruff check apps tests scripts` | Passed |
| `.venv/bin/ruff format --check apps tests scripts` | Passed; 83 files |
| `.venv/bin/mypy` | Passed; no issues in 83 source files |
| `npm run lint` | Passed |
| `npm run typecheck` | Passed; contracts, web and checks |
| Production `npm run build` | Passed; no backend connection is required at build time |
| `.venv/bin/python scripts/test_web.py` | **110 passed (2.5 minutes)** across all five viewport projects; production server, real auth/owned reads, axe, keyboard/focus, error states, screenshot comparisons; no skips or snapshot updates |
| `.venv/bin/python scripts/test_web.py tests/e2e/foundation.spec.ts` | **5 passed in 10.6 seconds** after descriptive page titles were added; rebuilt production source; all five login title/axe/screenshot checks passed without updating references |
| `PYTHONPATH=apps/api:apps/worker .venv/bin/pytest tests/unit -q --maxfail=1 --tb=short` | **203 passed in 27.07 seconds** |
| Docker API `uv run --no-sync pytest tests/integration -q --tb=short` | **292 passed in 307.88 seconds**, real PostgreSQL/Redis; includes migration/model drift and prior milestones |
| `CONTRACT_PYTHON=.venv/bin/python npm run contracts:check` | Passed; generated contracts unchanged |
| `node --test tests/contracts.test.mjs` | **7 passed**, zero skipped |
| `git diff --check` | Passed |
| Online `npm audit --json` | Completed with findings: 7 high/1 critical unchanged package entries; see dependency audit below |

All requested automated implementation checks completed. Browser tests passed with zero axe violations in scanned states. Manual screenshot/contrast review and keyboard/focus walkthroughs were performed; actual screen-reader speech and other browser engines remain unverified as stated below. No hosted CI result or full WCAG certification is claimed. A clean dependency security audit is not claimed.

The initial screenshot references were established through an explicit update run. Subsequent comparison found five expected reversal differences after the fixture's current-submission approval evidence was corrected; those five references were reviewed and refreshed, then the final complete run passed without snapshot updates. Correction/service examples were also checked after fixture refinement. No screenshot threshold, authorization check, or assertion was weakened to suppress a product failure. Initial test iterations fixed readiness, hidden mobile navigation targeting, route-announcer targeting and fixture-only session/fault races. The final runner cleans up its own loopback services and generated database; neither port 3100 nor 8010 remained listening after completion.

Warnings were the existing Python Starlette/httpx and Alembic deprecations (905 warnings in the live suite), plus Playwright's NO_COLOR/FORCE_COLOR warning. Registry/Docker/browser access denied by the sandbox was rerun with approved escalation and completed; no automated check remains blocked by those permissions.

## UX compromises and verification limits

- Live workflow actions and queue data are intentionally not enabled in 6A. They require 6B's backend-authoritative capability response and approved read contracts, not frontend permission inference.
- The current API exposes IDs rather than authorized directory names. Other people/departments display labeled identifiers; the signed-in owner displays their real name. No global directory was invented.
- Organization display timezone and live policy-window configuration are not exposed. Events show explicit UTC; the UI never decides leave/reopen eligibility from a local clock or synthetic threshold.
- Evidence endpoints paginate their arrays separately. A snapshot may be outside the loaded page; the UI says so rather than inventing it. Request detail's event history is currently returned in full by the existing API.
- After sign-in the user returns Home. No automatic mutation replay or persisted sensitive draft/return-state mechanism exists.
- Chromium was used for the five sizes. Browser automation verifies actual keyboard/focus behavior; manual screenshot/contrast/code review was performed. VoiceOver/NVDA spoken-output testing and Safari/Firefox were not performed. No WCAG conformance certification is claimed.
- Sixty reviewed macOS reference screenshots exist. Other platforms check consecutive-render consistency and emit reviewable attachments until platform-specific system-font references are established. Linux pixel baselines and a hosted CI rerun are not claimed.

## Dependency audit

Approved new primitives/icons/axe are pinned and locked as recorded in ADR 0006. No unapproved UI/state/form/design library was installed. Online `npm audit` reported 8 package entries (7 high, 1 critical). All eight affected package versions are unchanged from the accepted HEAD lockfile: Next 16.3.5, eslint-config-next/plugin 16.3.5, braces 3.0.3, fast-glob 3.3.1, micromatch 4.0.8, sharp 0.35.4 and source-map-js 1.2.1. None is a newly added approved primitive/icon/axe package.

The critical entry includes Next's next/og ImageResponse RCE advisory GHSA-vcvr-r3jv-pc5j; the UI does not add an ImageResponse route, but no exploitability exemption or clean security audit is claimed. npm proposes a Next update to 16.4.1 and other dependency remediation. No auto-fix, unrelated framework upgrade or advisory suppression was made inside 6A. This remains an explicit maintenance/security finding requiring reviewed remediation before an external pilot. Offline audit returned zero without reliable registry evidence and is not treated as a clean audit; the online result above is authoritative for this check.

## Changed areas

Web app route groups, tokens/scoped styles, shell/auth/read/evidence components, allowlisted adapter and generated transport aliases; six approved dependencies/npm lock; server-only Compose web upstream; five-project browser tests and macOS references; isolated browser fixture/runner and Make test-web; README/engineering/scope documentation and ADR 0006. Backend runtime, authentication/session/CSRF architecture, Redis/Celery behavior, policies, migrations and contracts are unchanged. No deployment, paid service, AI, notifications, analytics, uploads, payments or 6B implementation.
