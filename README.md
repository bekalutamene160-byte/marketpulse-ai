# MarketPulse AI

*Know the market. Anticipate the move.*

AI market intelligence and product discovery for electronics retailers.

**Source of truth:** [`MARKETPULSE_AI_SYSTEM_DESIGN.md`](MARKETPULSE_AI_SYSTEM_DESIGN.md). Every phase is built to its
roadmap (section 20) and exit gate. Deviations are recorded as ADRs in [`docs/adr`](docs/adr).

## Status

Phase 2 of 16: application shell, frontend foundations, and real authentication. See
[`docs/PHASE2_REPORT.md`](docs/PHASE2_REPORT.md) for the exit-gate evidence,
[`docs/PHASE1_REPORT.md`](docs/PHASE1_REPORT.md) for Phase 1, and
[`docs/PHASE0_REPORT.md`](docs/PHASE0_REPORT.md) for Phase 0.

## Layout

```
backend/    FastAPI API + Dramatiq worker (Python 3.12, uv)     -> backend/src/marketpulse
            Alembic migrations + the tenant foundation schema    -> backend/migrations, scripts/db
frontend/   React + TypeScript + Vite
docs/       ARCHITECTURE, SECURITY (threat model), DEPLOYMENT, DATA_MODEL, adr/ (decisions)
.github/    CI skeleton
docker-compose.yml   optional local PostgreSQL + Redis
```

## Quick start

Full step-by-step instructions, including Neon and Redis Cloud setup: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

```powershell
cd backend
uv sync
copy .env.example .env     # add your Neon direct + pooled URLs, app role password, Redis URL
uv run python scripts\db\bootstrap_app_role.py   # one-time: creates the NOBYPASSRLS app role
uv run alembic upgrade head                       # tables, indexes, RLS, grants, auth_sessions
uv run pytest
uv run uvicorn marketpulse.main:create_app --factory --reload

cd ..\frontend
npm ci
npm run dev                       # http://localhost:5173 -> register, sign in, use the shell
```

## Quality gates (run before every commit)

```powershell
cd backend  ; uv run ruff check . ; uv run ruff format --check . ; uv run mypy ; uv run pytest
cd backend  ; uv run pytest -m integration        # Phase 1: migration, RLS, two-tenant isolation (needs DB)
cd frontend ; npm run lint ; npm run typecheck ; npm test ; npm run build
```

## Principles (blueprint section 2)
Evidence over opinion. Deterministic code computes every number; an LLM only explains. The core works
with the LLM switched off. Public data only, within each source's terms. No secrets in git.
