# Security maintenance: npm dependencies, 2026-10-15

Owner-authorized security maintenance after completed Milestone 6A. No Milestone
6B, product/UI changes, unrelated modernization, advisory suppressions, forced
fixes, commits or pushes. Only the web manifest, npm lockfile and this report change.

## Audit evidence and result

Online `npm audit --json --fetch-retries=0 --fetch-timeout=15000` reproduced the
accepted finding: **7 high, 1 critical, 8 affected package entries**. These are
package-level aggregate counts, not counts of distinct advisories. The Next entry
contains seven advisories, including lower-severity issues hidden by that aggregate.
The first sandboxed attempt failed DNS; only the subsequent successful live registry
response is used as evidence. A nonzero audit exit indicates remaining findings,
not a registry error; the before/after JSON both contain complete vulnerability data.

After remediation the same full online audit reports **5 high, 0 critical** (all
other severity counts zero). A separate online `npm audit --omit=dev --json` reports
**0 vulnerabilities**. This does not erase the remaining development findings or
certify overall application security. Raw before/after/production registry JSON and
the complete package change list are retained locally in `.local/security-maintenance/`.

## Smallest reviewed remediation

- Pin `next` **16.3.5 → 16.4.1**. While 16.3.8 fixes the advisories in the npm
  response, the newer official typed-array/cache critical advisory includes every
  16.x release through 16.4.0. **16.4.1 is the smallest published 16.x release
  covering all reviewed advisories**, not simply an adoption of npm's suggestion.
  Review: [16.3.6](https://github.com/vercel/next.js/releases/tag/v16.3.6),
  [16.3.8](https://github.com/vercel/next.js/releases/tag/v16.3.8),
  [16.4.0](https://github.com/vercel/next.js/releases/tag/v16.4.0) and
  [16.4.1](https://github.com/vercel/next.js/releases/tag/v16.4.1).
- Pin `eslint-config-next` **16.3.5 → 16.4.1**, which requires its matching
  `@next/eslint-plugin-next` **16.4.1**. The config has no strict peer on the Next
  runtime; matching them is the compatible project convention, not a claim that
  mismatched runtime/config versions cannot install. Published config peers accept
  existing ESLint 9 and TypeScript 5; Next's React peers accept existing React 19.3.0.
- Next 16.4.1 raises its optional `sharp` range to `^0.35.5`, resolving **0.35.4 →
  0.35.5** and the corresponding prebuilt binaries. Native inspection confirms
  `sharp.versions.rsvg === '2.63.2'`, the patched librsvg version.
- Targeted `npm update source-map-js --save=false --no-audit --no-fund` resolves
  **1.2.1 → 1.2.2**, within the existing PostCSS range. No new direct dependency or
  override is required.

Installation used `npm install --no-audit --no-fund` after changing the two exact
manifest pins, followed by the targeted leaf update and a successful clean
`npm ci --no-audit --no-fund`. npm generated all registry URLs/integrity hashes.
The diff retains all platform-specific optional binaries; no packages were removed
or newly added. Exactly 40 locked package versions change, listed below. Apart
from the web workspace's manifest references, no same-version lock entry changes.
React/React DOM remain **19.3.0**. Radix, Lucide, axe, Playwright, TypeScript,
openapi-typescript, ESLint itself, Node/container pins and Python/uv dependencies
remain unchanged. No `npm audit fix`, major upgrade/downgrade or suppression was used.

## Every affected package entry

“Chain” below means the single underlying braces advisory, not additional CVEs.
Versions are the installed/locked before and after values. Feature assessments are
source-review observations, not exploitability guarantees or reasons to skip fixes.

| Package | Audit severity | Direct/transitive | Before → after | Advisory / fixed release | ActionDesk path and result |
| --- | --- | --- | --- | --- | --- |
| `next` | Critical aggregate | Direct runtime | 16.3.5 → 16.4.1 | Seven audited advisories, detailed below; latest reviewed fixes require 16.4.1 | App Router, server rendering, route handlers and development server are used. Removed from audit. |
| `sharp` | High | Transitive runtime, Next optional dependency | 0.35.4 → 0.35.5 | [GHSA-wq5f-xc86-pv6w / CVE-2026-96889](https://github.com/lovell/sharp/security/advisories/GHSA-wq5f-xc86-pv6w); fixed ≥0.35.5 | No `next/image`, SVG upload/processing or custom image route is declared. Native image decoder remains installed; framework image infrastructure warrants patching. Removed from audit. |
| `source-map-js` | High | Transitive, Next → PostCSS | 1.2.1 → 1.2.2 | [GHSA-68fv-2mgg-jv7q / CVE-2026-93749](https://github.com/advisories/GHSA-68fv-2mgg-jv7q); affected ≥1.0.0 <1.2.2, fixed 1.2.2 | CSS/source-map tooling is exercised by builds. No application endpoint accepts indexed source maps; malicious build inputs remain relevant. Removed from audit. |
| `braces` | High | Transitive dev, micromatch → braces | 3.0.3 → 3.0.3 | [GHSA-vfj7-8cjw-p6xm / CVE-2026-93687](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm); affected ≤3.0.3; **no published patch** | Deeply nested glob patterns can exhaust the stack. Present in lint tooling; no runtime request field is passed into it by application code. Remains high. |
| `micromatch` | High, chain | Transitive dev | 4.0.8 → 4.0.8 | Same braces GHSA; no independent advisory or patched chain release | ESLint glob dependency. Remains high. |
| `fast-glob` | High, chain | Transitive dev | 3.3.1 → 3.3.1 | Same braces GHSA; no patched chain release | Next lint plugin uses it in root-directory discovery; patterns originate in repository/lint configuration. Remains high. |
| `@next/eslint-plugin-next` | High, chain | Transitive dev | 16.3.5 → 16.4.1 | Same braces GHSA; published 16.4.1 still pins fast-glob 3.3.1 | Executed by Next lint rules, not the application API. Remains high despite matching framework update. |
| `eslint-config-next` | High, chain | Direct dev | 16.3.5 → 16.4.1 | Same braces GHSA through plugin; no fixed supported chain release | Imported by ESLint configuration. Remains high. |

The registry confirms **braces 3.0.3 is still the latest published version** and
the reviewed advisory lists no patch. npm proposes `eslint-config-next@14.2.35`
as a major downgrade to avoid the chain, not a braces patch. That is outside the
approved compatibility boundary and was not applied. Arbitrary overrides, a
replacement glob implementation, local vendoring or disabling Next lint rules would
be broader/unreviewed changes. Retain these five visible findings pending an
upstream patch or separately approved tooling remediation. Build/lint denial of
service remains a residual risk for untrusted repository/configuration inputs;
“development-only” is not treated as “harmless.”

## Every audited Next advisory

All rows concern direct `next@16.3.5`; all are remediated by installed 16.4.1 and
absent from the post-change npm response. Ranges below come from the live audit;
for 16.3.8 fixes, official release notes also identify the fixes. Some publisher
advisory pages retain provisional version fields, so those are not silently
substituted for the registry/release evidence.

| Advisory | Severity | Affected range / first 16.x fix | Current feature/path assessment |
| --- | --- | --- | --- |
| [GHSA-vcvr-r3jv-pc5j](https://github.com/vercel/next.js/security/advisories/GHSA-vcvr-r3jv-pc5j): next/og ImageResponse RCE | Critical | ≥16.2.0 <16.3.6 / 16.3.6 | No ImageResponse/next/og or attacker-fed generated SVG route is declared. Framework dependency is patched regardless. |
| [GHSA-3w37-wq28-93x7 / CVE-2026-94544](https://github.com/vercel/next.js/security/advisories/GHSA-3w37-wq28-93x7): Draft Mode cache-fill disclosure | Moderate | ≥16.3.0 <16.3.8 / 16.3.8 | No Draft Mode, Cache Components or `use cache`; React `cache()` request memoization is a different mechanism. Authenticated fetches explicitly use no-store. |
| [GHSA-4jqv-mc3x-m676](https://github.com/vercel/next.js/security/advisories/GHSA-4jqv-mc3x-m676): self-hosted SSG/ISR cache poisoning | Moderate | ≥16.0.0 <16.3.8 / 16.3.8 | Self-hosted Next is used. Business pages are dynamic; no application ISR/revalidation configuration. Static framework output still exists; no blanket exemption claimed. |
| [GHSA-39w2-rjm5-chcv](https://github.com/vercel/next.js/security/advisories/GHSA-39w2-rjm5-chcv): development MCP disclosure | Low | ≥16.0.0 <16.3.8 / 16.3.8 | Local Compose runs next dev. Its framework development endpoints are relevant; not assessed as unused merely because the app has no MCP implementation. |
| [GHSA-f87g-xv8r-7p7x](https://github.com/vercel/next.js/security/advisories/GHSA-f87g-xv8r-7p7x): metadata-image dynamicParams bypass | Moderate | ≥16.0.0 <16.3.8 / 16.3.8 | No generated metadata-image route or dynamicParams=false boundary is declared. Static title/description metadata is used. |
| [GHSA-mcj8-r9mp-w47p](https://github.com/vercel/next.js/security/advisories/GHSA-mcj8-r9mp-w47p): SSG/ISR cross-user substitution/DoS | Moderate | ≥16.0.0 <16.3.8 / 16.3.8 | Same self-hosted/dynamic-page assessment above. User reads are no-store; framework cache code is still upgraded. |
| [GHSA-cjq9-62q9-8jv4](https://github.com/vercel/next.js/security/advisories/GHSA-cjq9-62q9-8jv4): Image Optimization SSRF | High | ≥16.0.0 <16.3.8 / 16.3.8 | No next/image or configured remote image patterns. Framework optimization dependency remains present, so lack of current UI use is not a reason to retain the vulnerable version. |

## Additional official advisories reviewed

These were not present in the reproduced npm response, but appeared in the
[16.4.1 official security release](https://github.com/vercel/next.js/releases/tag/v16.4.1)
and informed the minimum version selection. All are patched by 16.4.1.

| Advisory | Severity | Affected / patched | Current path |
| --- | --- | --- | --- |
| [GHSA-673q-mjm6-r5xr](https://github.com/vercel/next.js/security/advisories/GHSA-673q-mjm6-r5xr): typed-array `use cache` RCE | Critical | Next ≥16.0.0 ≤16.4.0 / 16.4.1 | No Cache Components or use-cache typed-array functions; publisher still recommends upgrading. |
| [GHSA-2464-fhr4-w9xw](https://github.com/vercel/next.js/security/advisories/GHSA-2464-fhr4-w9xw): SVG Image Optimization RCE | Critical | Publisher lists 16.x >16.0.0 ≤16.4.0 / 16.4.1; sharp ≥0.35.5 also addresses underlying decoder | No current image-processing UI; glibc Linux is part of the development/CI stack. Both Next and sharp are upgraded. |
| [GHSA-p3m5-59mp-jv5r](https://github.com/vercel/next.js/security/advisories/GHSA-p3m5-59mp-jv5r): Server Actions DoS | High | Next ≥16.0.0 ≤16.4.0 / 16.4.1 | App Router is used; no `use server` Server Action is declared. Auth uses route-handler JSON POST and the safe native POST fallback. |

## Validation

All requested checks completed; none are blocked. No screenshot baseline or test
assertion changes were needed.

| Check | Exact result |
| --- | --- |
| `npm ci --no-audit --no-fund` | Passed; installed 416 packages from the lockfile |
| Full online `npm audit --json` | Before: 7 high + 1 critical. After: 5 high + 0 critical. Both exit 1 for reported vulnerabilities, with valid registry data. |
| Online `npm audit --omit=dev --json` | Passed, exit 0; zero findings |
| `npm run build`, invoked by browser runner | Passed, Next 16.4.1 production webpack build |
| `npm run lint` | Passed |
| `npm run typecheck` | Passed: contracts, Next route types/web TypeScript and check scripts |
| `.venv/bin/python scripts/test_web.py` | **160 passed, 3.0m**, complete browser suite; no retries or snapshot updates |
| `CONTRACT_PYTHON=.venv/bin/python node --test tests/contracts.test.mjs` | **7 passed**, 0 skipped, 19.10s |
| `CONTRACT_PYTHON=.venv/bin/python npm run contracts:check` | Passed; generated artifacts match FastAPI OpenAPI |
| `.venv/bin/python -m pytest tests/unit -q` | **204 passed**, 1 warning, 36.67s |
| `docker compose --env-file .env -f infra/compose.yaml -f infra/compose.local.yaml --profile checks run --rm checks` | **292 passed**, 905 warnings, 297.49s; live PostgreSQL/Redis and migration/model compatibility guards |
| Lockfile diff review | Exactly 40 related version updates; React/approved UI/tooling unchanged; no additions/removals or unrelated metadata churn |
| `git diff --check` | Passed |

Browser validation used real isolated PostgreSQL authentication/read fixtures and
production Next, across desktop 1440, laptop 1280, tablet 768, mobile 390 and narrow
320 viewports. It includes POST-only/no-JS credential safety, hydration, CSRF/logout,
owned-data visibility, accessibility, focus/copy and screenshot regressions. The
runner cleaned up its generated database and temporary API/web processes.

Local npm/build/browser checks used **Node 26.4.0 / npm 11.17.0 on macOS**. Live
backend checks used **Python 3.12.14 on Linux** (local Python unit checks: 3.12).
The repository's Node 22 CI/container pins remain unchanged; the selected Next
release declares Node >=20.9.0 and accepts the existing React/TypeScript/ESLint
versions. No hosted CI run or full Linux browser/build run is claimed.

Warnings: unchanged Starlette/httpx and Alembic deprecations; Playwright's
NO_COLOR/FORCE_COLOR notice; npm's deprecation notice for existing ESLint 9.39.5
and an uncovered install-script notice for unchanged `unrs-resolver@1.12.2`.
No install-script trust settings or unrelated packages were changed to silence
these warnings; clean install, lint, generation and production build all succeeded.
Neither a zero-finding full audit nor a general security certification is claimed.

## Complete lockfile version changes

All 40 entries, including optional platform binaries:

| Package | Before | After |
| --- | --- | --- |
| `@img/sharp-darwin-arm64` | 0.35.4 | 0.35.5 |
| `@img/sharp-darwin-x64` | 0.35.4 | 0.35.5 |
| `@img/sharp-freebsd-wasm32` | 0.35.4 | 0.35.5 |
| `@img/sharp-libvips-darwin-arm64` | 1.3.3 | 1.3.4 |
| `@img/sharp-libvips-darwin-x64` | 1.3.3 | 1.3.4 |
| `@img/sharp-libvips-linux-arm` | 1.3.3 | 1.3.4 |
| `@img/sharp-libvips-linux-arm64` | 1.3.3 | 1.3.4 |
| `@img/sharp-libvips-linux-ppc64` | 1.3.3 | 1.3.4 |
| `@img/sharp-libvips-linux-riscv64` | 1.3.3 | 1.3.4 |
| `@img/sharp-libvips-linux-s390x` | 1.3.3 | 1.3.4 |
| `@img/sharp-libvips-linux-x64` | 1.3.3 | 1.3.4 |
| `@img/sharp-libvips-linuxmusl-arm64` | 1.3.3 | 1.3.4 |
| `@img/sharp-libvips-linuxmusl-x64` | 1.3.3 | 1.3.4 |
| `@img/sharp-linux-arm` | 0.35.4 | 0.35.5 |
| `@img/sharp-linux-arm64` | 0.35.4 | 0.35.5 |
| `@img/sharp-linux-ppc64` | 0.35.4 | 0.35.5 |
| `@img/sharp-linux-riscv64` | 0.35.4 | 0.35.5 |
| `@img/sharp-linux-s390x` | 0.35.4 | 0.35.5 |
| `@img/sharp-linux-x64` | 0.35.4 | 0.35.5 |
| `@img/sharp-linuxmusl-arm64` | 0.35.4 | 0.35.5 |
| `@img/sharp-linuxmusl-x64` | 0.35.4 | 0.35.5 |
| `@img/sharp-wasm32` | 0.35.4 | 0.35.5 |
| `@img/sharp-webcontainers-wasm32` | 0.35.4 | 0.35.5 |
| `@img/sharp-win32-arm64` | 0.35.4 | 0.35.5 |
| `@img/sharp-win32-ia32` | 0.35.4 | 0.35.5 |
| `@img/sharp-win32-x64` | 0.35.4 | 0.35.5 |
| `@next/env` | 16.3.5 | 16.4.1 |
| `@next/eslint-plugin-next` | 16.3.5 | 16.4.1 |
| `@next/swc-darwin-arm64` | 16.3.5 | 16.4.1 |
| `@next/swc-darwin-x64` | 16.3.5 | 16.4.1 |
| `@next/swc-linux-arm64-gnu` | 16.3.5 | 16.4.1 |
| `@next/swc-linux-arm64-musl` | 16.3.5 | 16.4.1 |
| `@next/swc-linux-x64-gnu` | 16.3.5 | 16.4.1 |
| `@next/swc-linux-x64-musl` | 16.3.5 | 16.4.1 |
| `@next/swc-win32-arm64-msvc` | 16.3.5 | 16.4.1 |
| `@next/swc-win32-x64-msvc` | 16.3.5 | 16.4.1 |
| `eslint-config-next` | 16.3.5 | 16.4.1 |
| `next` | 16.3.5 | 16.4.1 |
| `sharp` | 0.35.4 | 0.35.5 |
| `source-map-js` | 1.2.1 | 1.2.2 |
