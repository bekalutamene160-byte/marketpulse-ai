# Phase 0 report: exit gate evidence

Blueprint section 20, Phase 0. Date: 2026-11-20.

**Build list:** monorepo structure, README, `.env.example`, ADR template, threat model, CI skeleton,
Docker Compose skeleton, dependency lockfiles.

**Exit gate:** frontend, API, worker, PostgreSQL, and Redis can start locally; health endpoints work;
lint/test commands documented; no secrets committed.

## Build list

| Item | Status | Where |
|---|---|---|
| Monorepo structure (blueprint 5.4 layout) | done | `backend/src/marketpulse/`, `frontend/`, `docs/` |
| README | done | `README.md` |
| `.env.example` | done | `backend/.env.example`, `frontend/.env.example` |
| ADR template and baseline ADRs | done | `docs/adr/0000` to `0020` (18 baseline + 2 deviations) |
| Threat model | done | `docs/SECURITY.md` |
| CI skeleton | written, **not executed** | `.github/workflows/ci.yml` |
| Docker Compose skeleton | written, **not executed** | `docker-compose.yml` (no Docker daemon available) |
| Dependency lockfiles | done | `backend/uv.lock`, `frontend/package-lock.json` |

## Exit gate

| Gate item | Result | Evidence |
|---|---|---|
| API starts | PASS | started with the documented `uvicorn ... --factory` command |
| Health endpoints work | PASS | `/health/live` 200; `/health/ready` 200 with database and redis `ok`, and 503 when the database is unset |
| Worker starts and runs a task | PASS | `dramatiq marketpulse.worker.app` started; an enqueued `ping` task executed |
| PostgreSQL reachable | PASS (local stand-in) | integration tests and `/health/ready` against a real embedded PostgreSQL |
| Redis reachable | PASS (local stand-in) | integration tests and the worker against a real Redis server |
| Frontend starts | PASS (built, not browser-run) | `npm run build` succeeds; 5 component tests pass |
| Lint and test commands documented | PASS | README and `docs/DEPLOYMENT.md` section 6 |
| No secrets committed | PASS | scan found only test fixtures and a documented throwaway dev password; no `.env`, no private keys |

## Check results

| Check | Result |
|---|---|
| `ruff check` / `ruff format --check` | clean |
| `mypy` (strict) | no issues in 29 source files |
| `pytest` (backend) | 55 passed |
| `pytest -m integration` | 2 passed (real PostgreSQL and Redis) |
| `eslint` / `tsc` (frontend) | clean |
| `vitest` | 5 passed |
| `vite build` | succeeds |
| `pip-audit` / `npm audit` | no known vulnerabilities |

## Honest limits of this evidence
1. The PostgreSQL and Redis above were local stand-ins in the authoring environment. **Your own Neon
   and Redis Cloud connections are unproven until you run `uv run pytest -m integration` on your machine.**
2. Nothing was run on Windows. Dramatiq's and psycopg's Windows behavior is the highest-risk part.
3. `docker-compose.yml` and the CI workflow have never been executed.
4. The frontend was built and unit-tested, not opened in a browser.
5. The Redis Cloud free-plan limits are unconfirmed (ADR-0020).

## Differences from the blueprint
- ADR-0019: managed PostgreSQL and Redis for development instead of local Docker.
- ADR-0020: Redis Cloud instead of Upstash for the broker (measured, not assumed).
- Worker, scheduler and frontend run on the host in Phase 0, not in containers; a scheduler stub
  is not created because nothing exists for it to schedule until Phase 5.

## Next
Phase 1 starts only after you have run the checks on your own machine and the open items above are
resolved or accepted. Phase 1 first decision: database session strategy (sync or async) given the
Windows event-loop limitation noted in `docs/ARCHITECTURE.md`.
