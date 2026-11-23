# Architecture (Phase 2)

The product design lives in `MARKETPULSE_AI_SYSTEM_DESIGN.md` and is the source of truth. This file
only describes what exists in the repository today and how it maps to the blueprint.

## Layers (blueprint 5.4)

```
backend/src/marketpulse/
  domain/          pure business rules. No frameworks, no SDKs.
    tenancy.py     Role, MembershipStatus, UserStatus enums
    audit.py       AuditAction enum
    entities.py    Organization, Workspace, User, Membership, AuditEvent (frozen dataclasses)
  application/     use cases and ports (interfaces)
    ports/         HealthProbe, TenantContextResolver, AuditEventWriter, repository protocols
    services/      ReadinessService, TenantContextService, AuditService,
                   OrganizationService, WorkspaceService, TenantProvisioningService
  infrastructure/  adapters implementing ports against real systems
    db/            base, models (5 ORM tables), session (engine+tenant GUC), repositories, audit
    queue/         Redis probe
    tenancy/       HeaderTenantContextResolver (dev/test, ADR-0024)
  api/             FastAPI: routers, schemas, middleware, error envelope, dependencies
  worker/          Dramatiq entrypoint (separate OS process from the API)
  core/            cross-cutting: logging, errors, tenancy, security, ids, clock
  config.py        typed, validated settings
  main.py          composition root: the only place adapters are wired to the application
migrations/        Alembic env + the initial schema migration (tables, indexes, RLS, grants)
```

Dependency direction: `api / worker -> application -> domain`, with `infrastructure` implementing
`application` ports. `tests/unit/test_architecture.py` fails the build if `domain` or `application`
imports a web framework, a vendor SDK, or an outer layer.

## Request flow (tenant-scoped endpoint)

```
GET /api/v1/organizations/current  (header X-MP-Organization: <uuid> in local/test)
  -> RequestContextMiddleware       assigns/validates X-Request-ID, times and logs the request
  -> get_tenant_context             HeaderTenantContextResolver -> TenantContext (401 if missing)
  -> get_db_session                 open session, BEGIN, set_config('app.tenant_id', ..., true)
  -> OrganizationService.get_current
       -> SqlAlchemyOrganizationRepository.get(id)
            SELECT ... WHERE id = ?   (RLS also filters: app.tenant_id must match)
  <- 200 with the org, or 404 if RLS hid it   (all under the error envelope)
  -> COMMIT (resets the transaction-local GUC) / ROLLBACK on error
```

## Session and tenant strategy (ADR-0021, ADR-0022)

- **Synchronous SQLAlchemy 2.x + psycopg3**, from sync `def` endpoints (threadpool). Chosen
  because psycopg async mode does not run on Windows' default event loop, and sync keeps the
  transaction boundary for `SET LOCAL` explicit.
- **Tenant context is transaction-local**: `set_config('app.tenant_id', :tid, true)` as the first
  statement in the request transaction. Bound parameter (no injection). Reset at COMMIT, so it
  cannot leak across PgBouncer-pooled connections (threat T10).
- **Row-level security** on `organizations`, `memberships`, `workspaces`, `audit_events`. Policy
  compares `organization_id` (or `id` for the org root) to `current_setting('app.tenant_id',
  true)`. `true` returns NULL when unset -> default-deny. `WITH CHECK` rejects inserts for the
  wrong tenant.
- **Two roles** (ADR-0023): the owner role on the DIRECT URL for migrations/provisioning; the
  `marketpulse_app` role (NOBYPASSRLS) on the POOLED URL for the API/worker. RLS is enforced
  against the app role; the owner bypasses it for admin work.

## Why these choices
- **Ports and adapters**: every use case is tested with fakes in milliseconds; the persistence
  layer can be swapped without touching business logic. The domain entities (frozen dataclasses)
  are the boundary between the ORM and the HTTP response, so no SQLAlchemy type reaches a client.
- **Double tenant filtering**: the repository adds an explicit `organization_id` predicate AND RLS
  filters at the database. Either alone is a defense; a missed WHERE cannot cross tenants.
- **Fail closed**: no tenant resolver configured -> 401. No DB -> 503. Production refuses the dev
  header resolver and requires TLS, no wildcard CORS, TLS Redis.

## Phase 2: authentication and the frontend shell

```
browser (localhost:5173)  --Vite proxy /api-->  FastAPI  ->  session resolver
   login/register screens            |                        |  cookie -> auth_sessions (digest)
   shell: sidebar, org selector      |                        v
   overview / members / status       +--> get_db_session: BEGIN; set_config(app.tenant_id + app.user_id)
                                                   -> RLS (tenant policies + per-user policies, ADR-0026)
```

- **Sessions (ADR-0025):** HttpOnly `mp_session` cookie holds an opaque token; only its
  SHA-256 digest is stored in `auth_sessions`. CSRF via `mp_csrf` + `X-CSRF-Token`, digest-bound
  to the session. Login/register rate limited per IP.
- **Signup** runs on the PRIVILEGED direct connection (org creation under RLS is impossible for
  the app role) and commits before the session row exists — FK visibility ordering.
- **Frontend:** React 19 + Vite + Tailwind 4 design tokens (dark navy / gold, blueprint 13.10),
  TanStack Query cache, react-hook-form + zod. No mock data in any customer screen.

## Not built yet (and which phase builds it)
Email verification and password reset (needs the email adapter, ADR-012), invitations, catalogue
(3), CSV import (4), durable queue and outbox (5), connectors (6), everything else per blueprint
section 20.

## Deviations from the blueprint
ADR-0019 (cloud Postgres/Redis for development), ADR-0020 (Redis Cloud over Upstash),
ADR-0021 (sync session strategy), ADR-0022 (SET LOCAL + RLS), ADR-0023 (app role bootstrap),
ADR-0024 (provisional dev header resolver until Phase 2 auth).
