# Running MarketPulse AI in development (cloud database and Redis)

Context: ADR-0019 and ADR-0020. Your laptop does not run Docker, so PostgreSQL and Redis come from
free cloud services. Console screens change over time; if a label below differs, follow the intent.

## 1. PostgreSQL on Neon

1. Create an account at neon.com and create a project. Pick the region closest to you.
2. Open the project's **Connect** dialog. You will see two connection strings:
   - **Pooled** (host contains `-pooler`): used by the application at runtime.
   - **Direct** (no `-pooler`): used for migrations and the app-role bootstrap from Phase 1 onward.
3. Put the **pooled** string in `backend/.env` as `MP_DATABASE_URL=...` and the **direct** string as
   `MP_DATABASE_DIRECT_URL=...`. Both already contain `sslmode=require`; keep it. Never commit this file.

Phase 1 uses two roles and two connections (ADR-0022, ADR-0023):
- The **direct** URL connects as the Neon project owner and is used by Alembic and the
  provisioning/bootstrap path only. It owns the tables and bypasses RLS for admin work.
- The **pooled** URL connects as the `marketpulse_app` role (created below) and is used by the API
  and worker. It owns no tables and has `NOBYPASSRLS`; RLS is enforced against it.

Know before you rely on it:
- The free plan scales the database to zero after 5 minutes idle. The first connection afterward can
  take a few seconds. This is normal, and why the readiness timeout is 10 seconds.
- Free plan limits at the time of writing: 1 GB storage and 100 compute hours per project per month.
  Do not leave a script polling `/health/ready` in a loop: it keeps the database awake and burns hours.

## 2. Redis on Redis Cloud

1. Create an account at redis.io (Redis Cloud) and create a **free** database.
2. Copy the endpoint and password, and build the URL: `rediss://default:<password>@<host>:<port>`.
   Use `rediss://` (two s) if the service offers TLS on that port. Use `redis://` only if it does not.
3. Put it in `backend/.env` as `MP_REDIS_URL=...`.
4. **Open question from ADR-0020:** in the console, find the free plan's throughput/command limit and
   any inactivity-deletion rule. Write the answer into ADR-0020.

## 3. Backend setup (Windows PowerShell)

Install once: Python 3.12+, `uv` (`winget install astral-sh.uv` or `pip install uv`), Node 22+, Git.

```powershell
cd marketpulse-ai\backend
uv sync                          # creates .venv and installs the locked dependencies
copy .env.example .env           # then edit .env and paste your URLs + app role password

# Phase 1 one-time database setup (run once per database, before the first migration):
uv run python scripts\db\bootstrap_app_role.py   # creates marketpulse_app with NOBYPASSRLS
uv run alembic upgrade head                      # creates tables, indexes, RLS policies, grants

uv run pytest                    # unit tests, need no network or services
uv run pytest -m integration     # proves Neon/Redis connectivity + Phase 1 RLS & tenant isolation
uv run uvicorn marketpulse.main:create_app --factory --reload
```

The `bootstrap_app_role.py` script reads `MP_DATABASE_DIRECT_URL` (owner) and `MP_DB_APP_PASSWORD`,
creates the `marketpulse_app` role idempotently with `NOBYPASSRLS`, and re-asserts
`rolbypassrls = false`. The migration then GRANTs it least-privilege privileges. After bootstrap,
edit `MP_DATABASE_URL` to point at the **pooled** string using the `marketpulse_app` user and the
password you set (e.g. `postgresql://marketpulse_app:<pw>@ep-...-pooler.<region>.aws.neon.tech/db?sslmode=require`).

Open http://127.0.0.1:8000/docs and try `GET /api/v1/health/live` and `GET /api/v1/health/ready`.
`ready` returns 503 until `MP_DATABASE_URL` is valid. That is the correct behavior, not a bug.

Phase 2 authentication (ADR-0025) — the normal way to use the app locally:
```powershell
# terminal 1: the API (needs the migration from section 3 first: alembic upgrade head)
uv run uvicorn marketpulse.main:create_app --factory --reload

# terminal 2: the frontend (Vite proxies /api to 127.0.0.1:8000, so cookies just work)
cd ..\frontend
npm ci
npm run dev                      # http://localhost:5173
```
Open http://localhost:5173/register, create an account (email, password of 12+ characters, an
organization name). You land in the shell with your real organization, a General workspace, and the
member list — all served by the session-authenticated, RLS-secured endpoints. Sign out and sign in
from the sidebar.

Phase 1 tenant endpoints also work WITHOUT a browser via the dev header (local/test only,
ADR-0024, set MP_ENABLE_DEV_TENANT_HEADER=true):
```
GET  /api/v1/organizations/current     header: X-MP-Organization: <uuid>
GET  /api/v1/workspaces                header: X-MP-Organization: <uuid>
POST /api/v1/workspaces                {"name": "..."}
GET  /api/v1/audit-events              header: X-MP-Organization: <uuid>
```
Without a session or header these return 401 UNAUTHORIZED. That is intentional and is also what a
production deployment does — there, ONLY the session cookie works.

## 4. Worker (second terminal)

```powershell
cd marketpulse-ai\backend
uv run dramatiq marketpulse.worker.app --processes 1 --threads 2
```

Keep concurrency low on your laptop (blueprint 19.1). The worker refuses to start without `MP_REDIS_URL`.
Windows is the least-tested platform for Dramatiq. If it fails to start, copy the full error to me
before changing anything.

## 5. Frontend

```powershell
cd marketpulse-ai\frontend
copy .env.example .env.local
npm ci
npm run dev                      # http://localhost:5173
```

## 6. The checks (run these before every commit)

```powershell
# backend
uv run ruff check . ; uv run ruff format --check . ; uv run mypy ; uv run pytest
# frontend
npm run lint ; npm run typecheck ; npm test ; npm run build
```

## 7. Optional: local infrastructure with Docker Compose

Only on a machine that can run Docker. Starts PostgreSQL and Redis with a throwaway password:

```
docker compose up -d
# then in backend/.env:
# MP_DATABASE_URL=postgresql://marketpulse:devpassword@127.0.0.1:5432/marketpulse
# MP_REDIS_URL=redis://127.0.0.1:6379/0
```

Note: the local PostgreSQL user is a superuser, which bypasses row-level security. Phase 1 creates a
separate non-superuser application role before any RLS test is trusted.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `/health/ready` returns 503, database `failed` | wrong or missing `MP_DATABASE_URL`, or the database is waking up; retry once |
| `/health/ready` database `not_configured` | `MP_DATABASE_URL` is empty |
| Worker exits: `MP_REDIS_URL is not set` | add the Redis URL to `backend/.env` |
| `ValidationError` on startup | a setting is invalid; the message names the field but never shows secret values |
| `uv: command not found` | install uv, reopen PowerShell |
| Port 8000 busy | add `--port 8001` |
