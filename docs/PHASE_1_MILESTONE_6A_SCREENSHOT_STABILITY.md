# Milestone 6A identifier screenshot stability

Scope: owner-requested investigation of the single laptop failure in CI run
38650528811, commit 32ef6f2. No application behavior, dependencies, authentication,
workflow authority or Milestone 6B functionality changes.

## Diagnosis

The failing screenshot was taken with the read-only UUID textarea focused and its
entire value selected by `Identifier.onFocus`. Clipboard operations and their live
announcements happen **after** this screenshot; they cannot explain this failure.
The preview uses fixed evidence timestamps. There is no dialog animation.

An instrumented production-browser reproduction of the same immediate-pair capture
failed on macOS on the second fresh context. Decoding both PNGs showed 26 genuinely
different pixels at x=384–895, y=396–399: the textarea's lower rounded border and
focus-outline corners, with small antialiasing differences. This was not merely a
PNG metadata/encoding difference. The textarea was positioned at y=335.5 with a
64px height; the centered dialog had a 277px height at y=221.5 on the 1280×720
viewport. Focus, selection (0–36), scroll positions, element geometry and loaded
fonts were identical before/between/after captures; there were no running DOM
animations. The instability is in the focused native control's rounded-edge
rendering, rather than a changing application value or workflow state.
Playwright already hides carets during these captures; adding a caret option would
not address the observed border/outline pixels.

Why CI exposed it: only Darwin screenshot references exist. That path uses
Playwright's screenshot matcher, which waits for stable captures and applies the
existing reference tolerance. Linux instead uses two immediate screenshots and
requires exact buffer equality. The laptop capture exposes rounded native-control
edges. It is not an exclusively Linux bug: exercising the immediate-pair path on
macOS reproduced it. The original CI run retained no artifacts, so its exact pixel
difference cannot be reconstructed or asserted to match the local 26-pixel result.

A matching Playwright 1.63.0 Ubuntu Noble container reproduced the original laptop
capture on the sixth fresh context: 14 changed pixels at x=390–889, y=396–398,
again at the textarea's bottom rounded border. The Linux textarea coordinates
were integer-aligned (y=335, height=64); fractional positioning is therefore not
a necessary cause. Focus, selection, fonts, scroll, geometry and animation state
again remained identical. This directly reproduces the CI comparison path on
Linux, without asserting knowledge of the missing original CI images.

The original test body was also run from a temporary read-only Linux diagnostic
copy with the modified helper: it failed on repetition 4 (3 passed, 1 failed,
16 not run). After adding on-disk PNG persistence, it failed on repetition 13
(12 passed, 1 failed, 7 not run). Both first/second files and both path attachments
were present; decoding this actual test's pair confirmed the same 14-pixel bounds
as the instrumented Linux reproduction. These were intentional diagnostic runs of
the original failing state, stopped at the first mismatch, not retries of the fix.

## Fix and retained coverage

The identifier test still verifies automatic textarea focus, the exact unchanged
UUID, read-only inspection and axe accessibility. It then clears the native text
selection and uses actual Tab navigation through Close to Copy, asserting both
focus targets. The screenshot captures the explicit keyboard-ready Copy state,
with the full unmasked UUID and a visible keyboard focus indicator. Product
selection, autofocus and copy behavior are unchanged. Clipboard success/failure
announcements, immutable UUID value and Escape focus restoration remain tested.
No sleeps, automatic retries, masks, comparison changes or tolerance increases
were introduced.

The five Darwin `identifier-dialog` references were deliberately refreshed for
this focus-state change; other screenshot references are untouched. Laptop and
320px screenshots were visually inspected, including full-ID wrapping.

The exact-pair helper now writes **both** PNGs into the test output directory and
attaches their paths before raising its unchanged assertion. Inline buffer
attachments alone are not persisted by the default list reporter; on-disk
persistence was verified against a real original-state Linux failure. A failure-only CI artifact step retains `test-results/` for seven days,
so future first/second images and error context can be compared after runner
cleanup. The previous helper attempted its only attachment after the assertion,
which made it unavailable on mismatch.

## Validation

| Check | Result |
| --- | --- |
| Instrumented stable laptop capture, macOS | 60 consecutive pairs, zero mismatches |
| Deliberate reference refresh | 5/5 passed; only identifier-dialog Darwin PNGs updated |
| Identifier test, macOS, `--repeat-each=10` | 50/50 passed, 3.3m; all five viewports, no snapshot updates or retries |
| Identifier test, Linux, `--repeat-each=10` | 50/50 passed, 3.2m; all five viewports, exact pair comparison, no retries |
| `npm run lint` | Passed |
| `npm run typecheck` | Passed |
| `npm run build` (inside the standard browser runner) | Passed |
| CI workflow YAML parse and executable-step checks | Passed |
| `.venv/bin/python scripts/test_web.py` (complete `make test-web` equivalent) | 160/160 passed, 3.2m, no retries or snapshot updates |
| `git diff --check` | Passed |

All five viewports were covered: 1440×1000, 1280×720, 768×1024, 390×844 and
320×740. The full suite used the normal isolated PostgreSQL/API fixture and
production web build on macOS. Linux validation covered the identifier test at all
five sizes, not the full 160-test suite. All requested checks completed; none remain
blocked. The normal runner stopped its own API/web processes and disposed of its
fixture database. Playwright emitted the existing NO_COLOR/FORCE_COLOR warning.

Targeted invocation on both platforms: `playwright test tests/e2e/design.spec.ts
--grep "tertiary identifiers" --repeat-each=10 --max-failures=1` (with the
appropriate base URL and writable output directory). Repetitions are independent
test runs; automatic retries remain disabled.

Linux runs used the matching official `mcr.microsoft.com/playwright:v1.63.0-noble`
image, a read-only repository mount and a temporary loopback proxy to the local
production Next server. Loopback preserved the normal secure-context clipboard
behavior without browser security flags. No Linux reference images were added.
The first image download was interrupted by an EOF and resumed successfully. An
initial Linux test launch stopped before tests because Playwright could not remove
a bind-mounted output directory; moving output to a writable child directory
resolved that harness issue. These are not hidden test retries.

The existing manual-review Compose stack on port 3000 was left running. Hosted CI
was not rerun; no changes were committed or pushed. Exact pixels from the
original CI failure are unavailable. No dependency, application or authentication change was needed.
