# Milestone 6A login credential URL leak

This security fix stays within Milestone 6A. No commit/push, dependency or schema change, or Milestone 6B work.

## Root cause and test gap

The server-rendered `LoginForm` had neither a `method` nor an `action`. HTML defaults selected GET to the current document URL and serialized the named `email` and `password` controls into its query string. The React handler called `preventDefault()` and performed the correct JSON POST, but that protection depended on successful hydration and handler attachment. Before hydration, or after unavailable/failed client scripts, the same form was an unsafe native GET form. Enter and click both had that failure path.

The missing native-form contract is established from the original source. The original manual incident's exact script failure or hydration timing cannot be reconstructed from its URL alone. Regression tests independently exercise disabled JavaScript, failed chunks and delayed hydration. No original credential or credential-bearing URL is read, printed or replayed during diagnosis.

The prior 110 browser checks exercised normal loaded/hydrated pages. Real authentication proved only the intercepted fetch path. None disabled/delayed scripts, asserted native method/action, checked credential-bearing GETs, or watched intermediate history/redirect URLs for credentials. They missed this security boundary.

## Fix

- Explicit `method="post"` and fixed action `/api/actiondesk/login-unavailable` in the SSR form. Labels, control names, username/current-password autocomplete, password visibility, Enter submission and validation remain intact.
- A dedicated POST-only Next route returns an empty 303 with fixed Location `/login?reason=javascript`, `Cache-Control: no-store` and `Referrer-Policy: no-referrer`. It never reads/parses, echoes, logs or forwards the body and performs no authentication/session action. The redirect GET and reloads contain no credentials.
- The login page explains that sign-in did not run and JavaScript/reloading is required. A `noscript` message provides guidance when scripts are disabled. No automatic retry or false success.
- Hydrated JSON POST still uses the existing adapter, actual browser Origin and backend authentication checks. Principal, cookies, CSRF and session-token handling are unchanged; no credential/token browser storage is added.

## Compromised local password

The prior initializer deliberately refused initialized accounts. The explicit `--reset-existing` option now replaces only an initialized local account in the configured organization, under the existing user lock/transaction. It uses existing `replace_password` to revoke every session atomically and preserves active/inactive status. No HTTP reset endpoint. Existing initialization/seeds remain unchanged. The CLI still requires an interactive local terminal and privately confirms a new 12–1024-character password.

```sh
docker compose --env-file .env -f infra/compose.yaml -f infra/compose.local.yaml exec api uv run --no-sync python -m app.core.init_account --email employee@actiondesk.ahmad --reset-existing
```

Enter a fresh password at the prompts. The compromised password is not required or reused; rotation is not performed automatically. Remove the old URL from browser history and address retained local log copies. This fix/rotation cannot retroactively erase earlier exposure.

## Regression coverage

`tests/e2e/login-security.spec.ts` adds seven scenarios per viewport: real successful click, real successful Enter, real failed login, native click without JavaScript, native Enter without JavaScript, failed client chunks and submission while hydration scripts are held. All five existing viewports run them. Assertions cover SSR method/action/autocomplete, POST destination, error UX, cookie absence after fallback, URL/query secrecy, GET/body restrictions, fixed redirects, back/forward history, titles, console/errors, unexpected credential/telemetry destinations and isolated API/web logs. Violation assertions retain labels rather than secret-bearing URLs/bodies. Test credentials are generated and synthetic, never the owner's password. No screenshot baseline/threshold changes.

The reset unit regression verifies old-password rejection, new-password login, all-device revocation, disabled-status preservation, and unknown/uninitialized-account rejection.

## Validation

| Check | Final result |
| --- | --- |
| `.venv/bin/python scripts/test_web.py tests/e2e/login-security.spec.ts --project=desktop --max-failures=1` | **7 passed, 6.1s**; disposable real PostgreSQL/Redis API and production web build |
| `.venv/bin/python scripts/test_web.py` (same complete runner used by `make test-web`) | **145 passed, 2.8 minutes**, no skips; 110 original cases plus 35 new security cases across five viewports; all 60 existing screenshot references matched without updates |
| `npm run build` | **Passed**, run by each browser wrapper before starting production web, including the final complete run |
| `npm run lint` | **Passed** after the final test-source changes |
| `npm run typecheck` | **Passed**, contracts/web/browser-check TypeScript, run after build completed |
| `PYTHONPATH=apps/api:apps/worker .venv/bin/pytest tests/unit/test_auth.py -q --tb=short` | **19 passed, 4.73s**; one existing Starlette deprecation warning |
| Ruff check and format check for the three changed Python files | **Passed**, 3 files formatted |
| `.venv/bin/mypy` | **Passed**, 83 source files |
| `git diff --check` | **Passed** |
| Running local `/login` SSR inspection | HTTP **200**, explicit native POST and safe action present |
| Running local CLI `--help` | **Passed**, `--reset-existing` available; no credentials changed |
| Local Compose service health | PostgreSQL, Redis, API, worker and web all **healthy**, left running |

Initial validation found a test-only ambiguous alert selector (Next's route announcer also has `role="alert"`); the assertion was scoped to the login form, then targeted and complete suites passed. An initial typecheck ran alongside build and raced Next's generated `.next/types` directory (ENOENT); rerunning after build completed passed. Neither issue required weakening a security assertion or changing application behavior. The temporary browser API/database were cleaned up by the runner; the manual-review stack was preserved. No original manual credential was accessed or reused. Password rotation remains for the owner to complete privately.

## Files changed for this fix

- `apps/web/components/login-form.tsx`
- `apps/web/app/login/page.tsx`
- `apps/web/app/api/actiondesk/login-unavailable/route.ts` (new)
- `apps/api/app/core/init_account.py`
- `apps/api/app/services/auth.py`
- `tests/e2e/login-security.spec.ts` (new)
- `tests/unit/test_auth.py`
- `README.md`
- `docs/PHASE_1_MILESTONE_6A.md`
- `docs/PHASE_1_MILESTONE_6A_LOGIN_SECURITY.md` (new)

All other pending Milestone 6A changes predate this fix.

## Development hydration follow-up

The owner's enabled-JavaScript fallback on the live Docker URL was reproduced in both the browser tool and a separately launched host Chromium at `http://127.0.0.1:3000/login`. Every requested client chunk returned 200, no CSP was present, and no React hydration-mismatch/runtime exception was reported. The form's React submit props were absent and password visibility did not respond. `LoginForm` was correctly marked `"use client"` and appeared in the delivered client chunks.

Console: repeated HMR WebSocket handshake `ERR_INVALID_HTTP_RESPONSE`, zero received HMR frames. Sanitized server logs identified the exact cause: `Blocked cross-origin request to Next.js dev resource /_next/hmr from "127.0.0.1"`. Installed Next 16.3.5's `block-cross-site-dev.js` permits localhost plus the bound hostname/configured origins. The container binds to `0.0.0.0`, so the documented browser host `127.0.0.1` was absent. Its rejection writes `Unauthorized` directly to the upgraded socket, explaining the invalid HTTP handshake response.

Next's development `app-index.js` creates a React debug channel and waits for the initial RSC response before calling `hydrateRoot`; the HMR path supplies the debug chunks/end marker. Blocking that channel stalled initial hydration without a form-level exception. As a causal control, changing only the browser URL to `localhost:3000` hydrated the same running app before any configuration change (submit handler present and password toggle worked). This rules out a missing client directive or stale build as the cause. Earlier checks used a production build, which does not depend on the development HMR/debug stream.

Narrow fix: `apps/web/next.config.ts` now explicitly lists `allowedDevOrigins: ["127.0.0.1"]`; only the web service was restarted. No wildcard, backend authentication-origin/CSRF change, dependency update, cache deletion, form fallback change, or rebuild was required. On the actual 127.0.0.1 stack afterward: `[HMR] connected`, React submit handler present, Enter sent JSON POST to `/api/actiondesk/auth/login`, and a nonexistent synthetic account got the expected inline 401 while remaining on clean `/login`. No real credential was used.

`tests/e2e/foundation.spec.ts` now exercises hydration/password visibility and intercepted JSON POST using a mocked generic 401, so it is safe against either the real development server or the isolated production test server. README documents the direct-development check, the HMR symptom and the explicit allowlist.

Follow-up validation:

- Against the actual running Docker development stack on port 3000: `npx playwright test tests/e2e/foundation.spec.ts tests/e2e/login-security.spec.ts --grep 'sign-in is readable|login hydrates|native|failed client chunks|submission while' --max-failures=1` — **30 passed in 40.6s**, five viewport sizes, no skips/updates. Hydration, mocked JSON POST, login screenshots/axe and all disabled/broken/delayed-script fallbacks passed.
- Isolated production comparison: `.venv/bin/python scripts/test_web.py tests/e2e/foundation.spec.ts tests/e2e/login-security.spec.ts --project=desktop --max-failures=1` — production build passed; **9 passed in 7.7s**, including real successful click/Enter authentication against disposable PostgreSQL/Redis and all safe-fallback cases. The complete production suite was not repeated for this development-only allowlist change.
- `npm run lint`, `npm run typecheck`, `git diff --check` — **passed**.
- Actual local API returned the expected safe 401 to a nonexistent synthetic login through JSON POST, with no fallback navigation. No real manual account/password was used or altered.
- All five manual-review services remained healthy and running. Temporary diagnostic browser artifacts were removed. Changes for this follow-up are limited to `apps/web/next.config.ts`, the foundation browser regression, README and this report. No commit/push.
