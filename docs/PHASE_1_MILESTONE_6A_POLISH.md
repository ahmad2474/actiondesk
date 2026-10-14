# Milestone 6A visual polish

Owner-authorized polish only: the approved palette/tokens, typography, navigation, request-detail architecture and component strategy are retained. No backend, dependencies, migrations, authentication/session handling or workflow mutations changed. No commit/push or Milestone 6B work.

## Small refinements

- Home uses less vertical padding at desktop/tablet widths. Below 768px, its duplicate creation CTA is omitted while the header's labeled **New request** link remains visible and keyboard accessible. The mobile hero retains comfortable internal spacing and unchanged copy/headings.
- The mobile account trigger is avatar-only; its full name, email and roles remain in the account menu. The tiny 320px creation-label override was removed. Menu/account/creation controls at tablet/mobile widths have at least 44px hit areas; the previous narrow account trigger was only 38px wide.
- A small shared `Identifier` inspector shows muted abbreviated IDs and exposes the original unchanged full value in an accessible Radix dialog. It supports select/copy, announces clipboard success or manual-copy guidance when clipboard access fails, restores focus, and includes full-value text for non-JavaScript rendering. Actor, department, request and policy values come solely from existing authorized evidence. Display abbreviations never become lookup/identity keys.
- Existing submission/work-cycle disclosures have quiet group borders, spacing and an accent on the current evidence group. Existing collapse defaults and all reasons/actors/timestamps are retained. The immutable newest-first timeline gains visual boundaries only at event sequences explicitly identified by received submission/cycle evidence; no event is removed, synthesized or reordered.
- Preview workflow dialogs retain explicit synthetic labels, “No live request will change,” simulation-only controls, server-authority language and existing rejection/processing consequences. Duplicate prose was shortened inside the private `PreviewAction` component. Shared dialog styling and identifier inspection contain no preview/workflow boilerplate; no live workflow dialogs/actions are introduced.

## Measured hero size and header hit areas

Measured against the running local development UI before and after the CSS changes. Sizes are pixels using the approved system font on the reviewed local platform.

| Viewport | Before | After | Reduction |
| --- | ---: | ---: | ---: |
| 1440 × 1000 | 165.8 | 133.8 | 19.3% |
| 1280 × 720 | 165.8 | 133.8 | 19.3% |
| 768 × 1024 | 165.8 | 133.8 | 19.3% |
| 390 × 844 | 249.6 | 189.6 | 24.0% |
| 320 × 740 | 280.4 | 220.4 | 21.4% |

At 390/320px, navigation and account triggers are 44 × 44; New request is approximately 136 × 44. At 768px, menu/account/creation targets also have 44px minimum height. Desktop controls and navigation architecture remain as before.

## Validation and screenshots

Screenshot review completed on the five configured sizes, including 320px full-ID wrapping, stacked dialog controls, long multi-line reasons and current/historical group boundaries. Explicit reference updates affected **37** of the original **60** PNGs; **23** original files remained byte-for-byte unchanged. **10** new dialog references bring the total to **70**. None were removed. Hashes were compared against a manifest captured before any updates.

| Existing references changed | Count |
| --- | ---: |
| `home-current-{desktop,laptop,tablet,mobile,narrow}-darwin.png` | 5 |
| `detail-{long,changes,reversal,service}-{desktop,laptop,tablet,mobile,narrow}-darwin.png` | 20 |
| `{requests,approvals,service,finance,create,revision}-current-{mobile,narrow}-darwin.png` | 12 |

Added `approval-dialog-{desktop,laptop,tablet,mobile,narrow}-darwin.png` and `identifier-dialog-{desktop,laptop,tablet,mobile,narrow}-darwin.png`. New dialog captures cover the viewport; existing page captures remain full-page. Existing login references are unchanged. Screenshot tolerance, five projects and platform-handling rules are unchanged.

| Validation | Exact result |
| --- | --- |
| `.venv/bin/python scripts/test_web.py` | **160 passed, 3.3 minutes**, complete production browser suite; no skips or snapshot updates; **70** screenshot references verified |
| `npx playwright test tests/e2e/foundation.spec.ts --grep 'login hydrates' --max-failures=1` | **5 passed, 9.8s**, actual Docker development server at port 3000, all five widths |
| `npm run build` | **Passed**, run by the production wrapper before the final complete suite |
| `npm run lint` | **Passed** after final source/test changes |
| `npm run typecheck` | **Passed**, contracts/web/browser-check TypeScript after final source/test changes |
| `git diff --check` | **Passed** |
| Local service health | PostgreSQL, Redis, API, worker, web all **healthy**, left running |

Reference preparation was explicit: **90 design browser checks passed (3.0m)** with reviewed screenshot updates, followed by **10 focused dialog checks (34.5s)** to capture the final read-only wrapping field and narrow stacked actions. The final 160-case production run above then verified all references without updates. No comparison thresholds, axe rules, focus assertions or login/security cases were removed or relaxed.

Coverage includes 1440 × 1000, 1280 × 720, 768 × 1024, 390 × 844 and 320 × 740; role-union navigation; loading/empty/error/conflict states; clipboard success/denial; original full UUID copying; current/historical submission and service-cycle evidence; keyboard dialogs and focus restoration; axe; real sign-in/session expiry; native safe POST fallback; failed/delayed client scripts; and unchanged development hydration configuration. No requested automated check is blocked. OS-specific baselines remain local Darwin references, with the existing platform-handling policy; actual screen-reader speech and Safari/Firefox were not tested in this pass.

Representative reviewed images: [390px Home](../tests/e2e/design.spec.ts-snapshots/home-current-mobile-darwin.png), [320px Home](../tests/e2e/design.spec.ts-snapshots/home-current-narrow-darwin.png), [320px full-ID inspector](../tests/e2e/design.spec.ts-snapshots/identifier-dialog-narrow-darwin.png), [320px preview dialog](../tests/e2e/design.spec.ts-snapshots/approval-dialog-narrow-darwin.png).

## Files

- `apps/web/components/design.module.css`
- `apps/web/components/identifier.tsx` (new, existing Radix primitive)
- `apps/web/components/request-detail.tsx`
- `apps/web/components/preview.tsx`
- `tests/e2e/design.spec.ts`
- `tests/e2e/visual.ts` (optional viewport-only capture for the new dialog screenshots; existing full-page captures and tolerances unchanged)
- Reviewed PNG references, this report and its milestone-report link.
