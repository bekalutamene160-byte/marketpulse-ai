# ADR 0021: Synchronous SQLAlchemy 2.x sessions with psycopg3 (threadpool)

- Status: accepted
- Date: 2026-11-20
- Blueprint reference: 5.4 (backend module boundaries), 6 (technology decisions), 19.1 (local development)

## Context
Phase 0's health probe used synchronous psycopg inside `asyncio.to_thread` because psycopg's
async mode refuses to run on Windows' default ProactorEventLoop, and the developer machine is
Windows (ADR-0019). Phase 1 must choose the real session strategy for the whole application, not
just a probe. The options are async SQLAlchemy with an async driver, or synchronous SQLAlchemy
accessed from sync FastAPI endpoints.

## Decision
Use synchronous SQLAlchemy 2.x with psycopg3, accessed from synchronous `def` FastAPI endpoints.
FastAPI runs sync endpoints in Starlette's threadpool automatically, so each request gets a
worker thread that can block on the database. The few async endpoints that exist (health) keep
using the Phase 0 `asyncio.to_thread` probe pattern.

## Alternatives considered
- **Async SQLAlchemy + asyncpg/psycopg async:** rejected as the primary path. On Windows the
  ProactorEventLoop incompatibility forces `asyncio.to_thread` shims anyway, and async SQLAlchemy
  complicates explicit transaction boundaries for `SET LOCAL` tenant context. The throughput at
  this stage does not justify the complexity.
- **Sync SQLAlchemy but called from `async def` endpoints via `to_thread`:** rejected. It hides
  the blocking call and tempts accidental `await`-free blocking inside the event loop. Sync `def`
  endpoints make the threadpool handoff explicit and automatic.

## Consequences
- Endpoints that touch the database are declared `def`, not `async def`. The few async endpoints
  (health) must not block the event loop.
- The session dependency opens a transaction, sets the tenant GUC, yields, and commits/rolls
  back (ADR-0022). The threadpool means many sessions can be open concurrently up to the
  Starlette threadpool size; the SQLAlchemy pool is sized small (Neon pooled endpoint already
  runs PgBouncer).
- A future high-throughput need can revisit async without rewriting the repository ports: the
  ports speak domain entities, not SQLAlchemy session types.

## Verification
`uv run mypy` and `uv run pytest` pass; `infrastructure/db/session.py` and `api/deps.get_db_session`
encode the strategy; the workspace and audit endpoints are sync `def`.
