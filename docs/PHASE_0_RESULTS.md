# Phase 0 verification results and closeout

14 October 2026. **Phase 0 is complete**, as confirmed by the project owner following successful local and GitHub Actions verification. Phase 1 has not been authorized or started.

This report supersedes the earlier incomplete verification report. Earlier sandbox, dependency, and Git initialization failures are historical observations, not outstanding Phase 0 blockers. The final runtime and hosted CI results below are owner-confirmed; this documentation closeout does not rerun those suites. No CI run identifier, test counts, or durations were supplied for the final run.

## Final verified state

| Check | Final result and evidence |
| --- | --- |
| Local development Compose stack | Passed; owner confirmed the base + local override stack verification. |
| CI-equivalent base Compose stack | Passed; owner confirmed verification without local host source mounts. |
| GitHub Actions foundation workflow | Passed; owner confirmed GitHub Actions is green. The configured verification command is `make verify COMPOSE_FILES="-f infra/compose.yaml"`. |
| Seed idempotence | Verified; owner confirmed repeated seeding creates no duplicates. |
| Full mypy | Passed; owner confirmed the final result. The workflow runs it through `make typecheck`. |
| Dependency locks and API contracts | `uv.lock` and `package-lock.json` are tracked. The passing workflow installs locked dependencies and runs contract generation/drift tests and `make contracts-check` using `openapi-typescript`. |

The passing workflow's `make verify` sequence includes Ruff lint/format, ESLint, Python and TypeScript type checks, unit and contract tests, Compose validation, stack startup with health verification, PostgreSQL integration tests, the no-op worker smoke check, Playwright smoke tests, and the Next.js production build. These results are attributed to the owner-confirmed passing workflow, not to new executions during closeout. No separate shutdown/restart result or additional environment probe is claimed here.

## Local and CI Compose separation

- `infra/compose.yaml` is the base configuration, with no host source bind mounts.
- `infra/compose.local.yaml` adds local source mounts/hot reload and the Next.js cache volume. Local Make targets select both files by default.
- CI selects only the base configuration, including recursive Make verification targets.
- The web image retains `USER node`; neither Compose configuration overrides it to root. No workspace `chmod 777` or root execution workaround was introduced.
- The web health probe remains enabled. The temporary startup inflation was reverted: web retries are 10, start period is 20 seconds, and Compose waits up to 180 seconds. CI service/health/log failure diagnostics remain in place.

The GitHub Actions failure was:

```text
EACCES: permission denied, open '/workspace/apps/web/next-env.d.ts'
```

The local development bind mount replaced the image-owned directory with the runner-owned checkout. Keeping that mount out of the base configuration preserves the directory writable by the non-root `node` user in CI. The successful base-stack and GitHub Actions verification confirms the reported permission issue is resolved; local development retains its source mounts.

## Documented commands

After `cp .env.example .env` and `make setup`:

```sh
make dev                                           # Local base + override startup
make verify                                        # Local foundation verification
make verify COMPOSE_FILES="-f infra/compose.yaml"     # CI-equivalent verification
make down                                          # Stop local stack; preserve volumes
make down COMPOSE_FILES="-f infra/compose.yaml"       # Stop base-only stack; preserve volumes
```

The schema remains migration-managed and the fixtures remain deterministic synthetic data. No application, domain, authorization, workflow, or AI changes were made during closeout.

## Documentation closeout checks

Only the following lightweight checks were rerun during this closeout:

| Exact command | Result |
| --- | --- |
| `git diff --check` | Passed; no whitespace errors. |
| `make compose-check` | Passed; both base and base + local configurations validate without requiring a Docker daemon. |
| `PYTHONPATH=apps/api:apps/worker .venv-checks/bin/python -m pytest tests/unit/test_compose.py -q` | Passed; 4 tests covering Compose mount separation, health probes, non-root configuration, CI shell syntax, and recursive Make selection. |

The working tree was clean at the start of closeout. Final Git status shows only `README.md` and `docs/PHASE_0_RESULTS.md` modified, both unstaged; there are no staged or untracked changes. The documentation is ready for a final Phase 0 closeout commit; no commit is made. Phase 1 remains on hold pending explicit approval.
