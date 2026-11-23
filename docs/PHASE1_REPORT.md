# MarketPulse AI: Phase 1 Report

**Phase:** 1 of 16, "Database foundation and tenant security" (blueprint section 20)
**Report date:** 2026-11-20
**Source of truth:** `MARKETPULSE_AI_SYSTEM_DESIGN.md`
**Status:** Phase 1 built and verified in the authoring environment. Unit tests, lint, format and
strict type checks are green and were re-run for this report. The integration tests (real
PostgreSQL migration + RLS + two-tenant isolation) are written and collect/skip cleanly, but the
authoring sandbox has no PostgreSQL server, so they were **not** executed here; they must be run
by the owner against Neon (section 10, evidence E2/E3/E4).

---

## 0. How to read this report

Every claim is tagged with how it is known. Nothing is stated as fact without a tag.

| Tag | Meaning |
|---|---|
| **[V-today]** | Re-run by the author for this report on 2026-11-20, output seen |
| **[V-earlier]** | Verified earlier in the authoring sandbox during Phase 1; not re-run for this report |
| **[U]** | Reported by the project owner (BK); no detail was supplied |
| **[X]** | Not verified by anyone |

The authoring sandbox is Linux, has no Docker daemon and no PostgreSQL/Redis server. The
migration SQL is verified by offline DDL generation (no connection) and by AST/structure tests;
the live migration and RLS behaviour require the owner's Neon database.

---

## 1. Scope: what Phase 1 required

From blueprint section 20.

**Build:** PostgreSQL connection/session lifecycle, SQLAlchemy models, Alembic migrations,
organizations, users, memberships, workspaces, tenant context, RLS, audit events.

**Exit gate:** migration from empty DB succeeds; two-tenant integration tests prove isolation;
unauthorized access returns correct errors; DB role cannot bypass RLS.

**Execution rules applied** (blueprint section 24): execute Phase 1 only; do not begin Phase 2
until the gate is met; never claim completion without running the required checks.

**Explicitly out of scope** (and correctly absent): authentication/login flows, sessions,
cookies, CSRF (Phase 2), the frontend shell (Phase 2), catalogue/products (Phase 3), the durable
queue/outbox (Phase 5), connectors (Phase 6), any LLM code.

---

## 2. Executive summary

- A **database foundation** is in place: SQLAlchemy 2.x models for the five tenant-foundation
  tables, an Alembic initial migration that creates them with indexes, row-level security policies
  and least-privilege grants, and a synchronous session lifecycle that sets the tenant identity
  per transaction.
- **Tenant isolation is enforced two ways:** an explicit `organization_id` predicate in every
  repository AND PostgreSQL row-level security with `USING` + `WITH CHECK` against the
  transaction-local `app.tenant_id` GUC. The system is **default-deny** until a tenant is set.
- A **least-privilege application role** `marketpulse_app` (`NOBYPASSRLS`) is created by a
  one-time bootstrap script; the migration GRANTs it only what it needs. The owner role on the
  direct URL handles migrations/provisioning.
- Quality gate **[V-today]**: backend 125 unit tests pass (9 integration deselected by design),
  ruff clean, formatter clean, mypy strict clean on 60 source files. The migration renders to
  valid PostgreSQL DDL offline (verified by a unit test that runs `alembic upgrade --sql`).
- Four new ADRs record the session strategy (0021), the tenant-context/RLS design (0022), the
  app-role bootstrap (0023), and the provisional dev header resolver replaced by Phase 2 auth
  (0024).
- **Gate verdict: conditional pass.** Met in the authoring environment for everything that does
  not need a live database. The exit gate's database-specific items (live migration, two-tenant
  isolation, `rolbypassrls = false`) depend on evidence E2–E4 in section 10, which the owner must
  record against Neon.

---

## 3. Exit-gate scorecard

| Gate item | Authoring environment | Owner's machine |
|---|---|---|
| Migration from empty DB succeeds | SQL verified by offline DDL generation + structure tests [V-today]; live upgrade not run (no DB) [X] | pending E2 [U] |
| Two-tenant integration tests prove isolation | tests written, collect and skip cleanly [V-today]; not run (no DB) [X] | pending E3 [U] |
| Unauthorized access returns correct errors | PASS: 401 without tenant context, 404 for hidden rows, error envelope shape [V-today] | n/a (unit) |
| DB role cannot bypass RLS | `bootstrap_app_role.py` asserts `rolbypassrls=false`; integration test asserts it [V-today, code]; live assertion pending E4 [X] | pending E4 [U] |

Build-list scorecard:

| Item | Status | Location |
|---|---|---|
| PostgreSQL connection/session lifecycle | done | `infrastructure/db/session.py`, `api/deps.get_db_session` |
| SQLAlchemy models | done | `infrastructure/db/models/*.py` |
| Alembic migrations | done | `migrations/env.py`, `migrations/versions/0001_initial_schema.py` |
| organizations, users, memberships, workspaces | done | models + migration |
| tenant context | done | `core/tenancy.py`, `application/services/tenancy.py`, `infrastructure/tenancy/header_resolver.py` |
| RLS | done | migration (ENABLE + policies with USING/WITH CHECK) |
| audit events | done | model, `AuditService`, `SqlAlchemyAuditWriter`, `audit_events` table |

---

## 4. What was built, and the logic behind it

### 4.1 Session strategy (ADR-0021)

Synchronous SQLAlchemy 2.x with psycopg3, from synchronous `def` FastAPI endpoints (run in
Starlette's threadpool). Chosen because psycopg's async mode does not run on Windows' default
ProactorEventLoop (the developer machine is Windows), and sync keeps the transaction boundary for
`SET LOCAL` explicit. The few async endpoints (health) keep the Phase 0 `asyncio.to_thread` probe
pattern.

### 4.2 Tenant context (ADR-0022, ADR-0024)

```
request  ->  TenantContextResolver (header in local/test; auth in Phase 2)
         ->  TenantContext (organization_id, optional workspace_id/user_id)
         ->  get_db_session: BEGIN; SELECT set_config('app.tenant_id', :tid, true); yield; COMMIT
         ->  repository adds explicit organization_id predicate; RLS filters at the DB
```

`set_config(name, value, true)` is equivalent to `SET LOCAL`: the bound `:tid` parameter means no
string interpolation (no injection surface), and `is_local=true` resets the GUC at COMMIT so it
cannot leak across PgBouncer-pooled connections (threat T10). A session with no tenant set reads
`current_setting('app.tenant_id', true)` as NULL, so every policy comparison is NULL → default-deny.

### 4.3 Row-level security (ADR-0022)

`ENABLE ROW LEVEL SECURITY` on `organizations`, `memberships`, `workspaces`, `audit_events`. Each
has a `<table>_tenant_isolation` policy `FOR ALL USING (...) WITH CHECK (...)`. `users` is global
(no RLS); access is mediated through the RLS-secured `memberships` join. The application role owns
no tables and has `NOBYPASSRLS` (ADR-0023), so RLS is enforced against it; the owner bypasses for
provisioning/migrations.

### 4.4 Two roles, two connections (ADR-0023)

| Role | URL | Used by | RLS |
|---|---|---|---|
| owner (Neon project owner / local superuser) | `MP_DATABASE_DIRECT_URL` (direct) | Alembic, bootstrap, provisioning | bypassed (admin) |
| `marketpulse_app` (`NOBYPASSRLS`) | `MP_DATABASE_URL` (pooled) | API, worker | enforced |

`scripts/db/bootstrap_app_role.py` creates the app role idempotently, composes role/password with
`psycopg.sql` (never f-strings), and re-asserts `rolbypassrls = false`. The migration GRANTs it
least-privilege privileges; it does not create the role.

### 4.5 Key design decisions and why

| Decision | Reason |
|---|---|
| Domain entities are frozen dataclasses, separate from ORM | Use cases are testable with fakes in ms; SQLAlchemy never reaches a client or a use case |
| Tenant filtering done TWICE (predicate + RLS) | Either alone is a defense; a missed WHERE cannot cross tenants |
| `set_config(..., true)` not `SET` | Transaction-local; survives PgBouncer transaction-mode pooling |
| `current_setting(..., true)` (NULL when unset) | Default-deny: no tenant → no rows, never another tenant's |
| `WITH CHECK` on every policy | Cannot INSERT a row for a different tenant even if a repository is misused |
| App role via bootstrap script, not the migration | Role lifecycle is a DBA concern; schema is an application concern; keeps migrations deterministic |
| `users` is global, no RLS | A user may join many orgs; member visibility comes through the RLS-secured memberships join |
| Dev header resolver, local/test only | Lets the tenant machinery run end to end before Phase 2 auth; forbidden in staging/production by `Settings` |
| Audit row commits in the caller's transaction | A crash between "create workspace" and "audit" cannot leave one without the other |
| Sync `def` endpoints for DB work | Threadpool handoff is explicit; no async-driver/Windows pitfalls |
| `pool_pre_ping` + small pool | Neon scale-to-zero leaves stale connections; PgBouncer already pools server-side |

---

## 5. File reference

### 5.1 New backend source (Phase 1 adds 31 files; mypy strict on 60 total)

| File | Purpose |
|---|---|
| `core/tenancy.py` | `TenantContext` (frozen), `tenant_context_var` ContextVar, `TenantContextError` |
| `core/security.py` | Argon2id `hash_password`/`verify_password`/`needs_rehash` (argon2-cffi) |
| `core/ids.py` | `new_id()` (uuid4), `is_valid_uuid_str()` |
| `core/clock.py` | `Clock` protocol, `SystemClock`, `utcnow()` |
| `domain/tenancy.py` | `Role`, `MembershipStatus`, `UserStatus` enums (pure) |
| `domain/audit.py` | `AuditAction` enum (pure) |
| `domain/entities.py` | `Organization`, `Workspace`, `User`, `Membership`, `AuditEvent` (frozen dataclasses) |
| `application/ports/tenancy.py` | `TenantContextResolver` protocol |
| `application/ports/audit.py` | `AuditEventWriter` protocol |
| `application/ports/repositories.py` | `OrganizationRepository`, `WorkspaceRepository`, `UserRepository`, `MembershipRepository`, `AuditEventRepository` protocols |
| `application/services/tenancy.py` | `TenantContextService` (resolve or 401) |
| `application/services/audit.py` | `AuditService` (record) |
| `application/services/organizations.py` | `OrganizationService.get_current` |
| `application/services/workspaces.py` | `WorkspaceService.list_for_current`, `.create` |
| `application/services/provisioning.py` | `TenantProvisioningService` (admin/bootstrap: org/user/membership) |
| `infrastructure/db/base.py` | SQLAlchemy `Base` with naming convention |
| `infrastructure/db/models/*.py` | `OrganizationORM`, `UserORM`, `MembershipORM`, `WorkspaceORM`, `AuditEventORM` |
| `infrastructure/db/session.py` | `DatabaseSessionManager`, `set_tenant_context`, `current_request_id` |
| `infrastructure/db/repositories.py` | SQLAlchemy repository adapters + ORM↔entity mappers |
| `infrastructure/db/audit.py` | `SqlAlchemyAuditWriter` |
| `infrastructure/tenancy/header_resolver.py` | `HeaderTenantContextResolver` (dev/test, ADR-0024) |
| `api/v1/schemas/tenancy.py` | Pydantic request/response models |
| `api/v1/routers/organizations.py`, `workspaces.py`, `audit_events.py` | tenant endpoints |
| `config.py` | extended: `database_direct_url`, `db_app_role`, `db_app_password`, `db_pool_*`, `enable_dev_tenant_header` + guardrails |
| `api/deps.py` | extended: `get_tenant_context`, `get_db_session`, service deps |
| `main.py` | extended: wires db_manager, tenant_resolver, clock; disposes engine on shutdown |

### 5.2 Migrations and tooling

| File | Purpose |
|---|---|
| `alembic.ini` | Alembic config |
| `migrations/env.py` | resolves DIRECT URL for migrations; offline SQL fallback; online guard |
| `migrations/script.py.mako` | revision template |
| `migrations/versions/0001_initial_schema.py` | tables, indexes, RLS policies, app-role grants |
| `scripts/db/bootstrap_app_role.py` | one-time NOBYPASSRLS app role creation |
| `pyproject.toml` | added sqlalchemy, alembic, argon2-cffi, sqlparse; ruff/mypy config |

### 5.3 Documentation

| File | Purpose |
|---|---|
| `docs/ARCHITECTURE.md` | updated to Phase 1: layers, request flow, session/tenant strategy |
| `docs/SECURITY.md` | T8/T9/T10 → done; T16 added; Phase 1 accepted risks |
| `docs/DEPLOYMENT.md` | two roles, bootstrap, migrate, tenant endpoints |
| `docs/DATA_MODEL.md` | new: table dictionary, indexes, RLS (blueprint 23) |
| `docs/adr/0021..0024` | session strategy, SET LOCAL + RLS, app role bootstrap, dev header resolver |
| `.github/workflows/ci.yml` | added a postgres service + bootstrap + migrate + integration step |

---

## 6. Tests

### 6.1 Strategy (unchanged from Phase 0)

Unit tests with fakes for logic; API tests through the FastAPI test client with injected fakes;
the architecture test fails the build on a layering violation; integration tests opt-in with
`-m integration` and skip when no DB URL is set. Failure paths tested as deliberately as success.

### 6.2 Backend: 125 unit tests [V-today]

| File | Count | What it proves |
|---|---|---|
| `test_architecture.py` | 4 | inner layers scanned; domain/application import no framework/SDK; no outer-layer imports; domain does not import application |
| `test_config.py` | 31 | Phase 0 config + Phase 1: direct URL scheme/blank/dsn, app role slug validation (rejects hyphens/metachars, accepts underscores), dev header forbidden in non-local, pool bounds |
| `test_health_api.py` | 13 | unchanged Phase 0 health behaviour still green |
| `test_tenancy.py` | 12 | TenantContext frozen + with_workspace; header resolver valid/lowercase/missing/invalid/ignores-bad-user; context service 401 with no resolver / none returned / resolves when valid |
| `test_tenant_api.py` | 10 | 401 without context; 200 with valid UUID header; 404 for unknown tenant; 401 for invalid UUID; workspace 201 + audit; validation 422; list scoped to tenant; audit list scoped + requires context |
| `test_models.py` | 8 | 5 tables registered; tenant tables have organization_id; users global; unique constraints; membership unique org+user; audit metadata JSONB; UUID PKs; each compiles to CREATE TABLE DDL |
| `test_migrations.py` | 7 | offline SQL creates all tables; RLS enabled on tenant tables, NOT on users; tenant_isolation policies with WITH CHECK + current_setting(...,true); least-privilege grants; indexes; upgrade/downgrade functions exist |
| `test_provisioning.py` | 6 | create org/user/membership; conflict 409 on dup slug/email (case-insensitive); password hashed (Argon2id, verify roundtrip); audit recorded under new tenant |
| `test_security.py` | 6 | hash/verify roundtrip; wrong password; malformed hash returns False not raise; empty rejected; hashes unique; needs_rehash False |
| `test_workspace_service.py` | 4 | create persists+audits with caller tenant; rejects blank/over-long name (422); list returns only current tenant |
| `test_organization_service.py` | 2 | get_current returns org; 404 when not visible |
| `test_audit_service.py` | 2 | record delegates with caller ctx; defaults metadata |
| `test_ids.py` | 3 | uuid4; valid/invalid uuid str |
| `test_logging.py` | 3 | unchanged Phase 0 |
| `test_probes.py` | 5 | unchanged Phase 0 |
| `test_readiness_service.py` | 7 | unchanged Phase 0 |
| `test_worker.py` | 2 | unchanged Phase 0 |

Total: 4 + 31 + 13 + 12 + 10 + 8 + 7 + 6 + 6 + 4 + 2 + 2 + 3 + 3 + 5 + 7 + 2 = **125** [V-today].
Phase 1 adds 70 unit tests on top of Phase 0's 55.

### 6.3 Backend integration: 9 tests (not run for this report)

`tests/integration/test_migrations_live.py` (3): tables exist; RLS enabled on tenant tables;
tenant_isolation policies exist. `tests/integration/test_rls.py` (3): app role `rolbypassrls =
false`; default-deny without tenant context (a seeded row is invisible); visibility under the
matching context. `tests/integration/test_tenant_isolation.py` (1): provision two tenants, assert
A sees only A and B sees only B, and that B's rows are invisible to A even when explicitly
requested by id. Plus Phase 0's `test_services_live.py` (2).

They collect and skip cleanly with no DB [V-today]. **Important:** a run that prints `9 skipped`
is **not** a pass. Evidence E2–E4 depend on `2+ passed` style results against Neon.

### 6.4 Static checks [V-today]

| Check | Result |
|---|---|
| `ruff check` | All checks passed |
| `ruff format --check` | 90 files already formatted |
| `mypy` (strict) | Success: no issues in 60 source files |
| `alembic upgrade head --sql` (offline) | renders all tables + RLS + grants [V-today] |

### 6.5 What the tests do not cover

- No live PostgreSQL execution in the authoring sandbox (no server). The migration SQL and RLS
  policy text are verified by offline generation and structure tests, not by a real upgrade.
- No concurrency/load test of the session pool under PgBouncer.
- The dev header resolver is exercised only in `test`/`local`; the Phase 2 auth resolver does not
  exist yet.
- `users` has no RLS by design; a direct cross-tenant "list users" path is not built and not
  exposed (Phase 2).

---

## 7. Deviations from the blueprint

| ID | Deviation | Reason | Status |
|---|---|---|---|
| ADR-0021 | Sync SQLAlchemy + threadpool, not async | psycopg async does not run on Windows' default event loop; sync keeps SET LOCAL transaction boundaries explicit | accepted |
| ADR-0022 | `set_config(..., true)` + RLS default-deny, no `FORCE` | transaction-local survives PgBouncer; FORCE varies by provider and could block provisioning | accepted |
| ADR-0023 | App role via bootstrap script, not the migration | role lifecycle ≠ schema lifecycle; keeps migrations deterministic | accepted |
| ADR-0024 | Dev header resolver for tenant context until Phase 2 | lets the tenant machinery run end to end before auth exists; forbidden in non-local | provisional (superseded by Phase 2) |
| note | Organization creation is an admin/bootstrap path, not a public `POST /organizations` | blueprint 14.1 is a contract, not permission to expose every operation; self-service signup is Phase 2 | accepted |

ADRs 0001–0020 are unchanged from Phase 0.

---

## 8. Security posture

`docs/SECURITY.md` now marks **T8, T9, T10 done** (Phase 1) and adds **T16** (client-supplied
tenant id trusted in production — mitigated by server-side resolution + the dev-header guard).

| Status | Threats |
|---|---|
| Done | T1, T2, T3, T4, T5, T6, T7, T8, T9, T10, T14 (lockfiles; CI job written), T15, T16 (provisional) |
| Planned | T11 (Phase 5), T12 (Phase 6), T13 (Phase 12) |

**Accepted risks (Phase 1):** no real authentication exists; the dev header resolver trusts
`X-MP-Organization` in local/test ONLY and the app refuses to start with it in staging/production.
Do not deploy publicly before Phase 2. The integration tests need a real PostgreSQL and skip
without one.

---

## 9. Known limitations and defects

1. **Integration tests not executed in the authoring sandbox** (no PostgreSQL). They are written,
   collect, and skip cleanly. The owner must run them against Neon and record E2–E4. [X]
2. **CI has still never run.** The workflow now includes a postgres service + bootstrap + migrate +
   integration step; its first execution is the first push to GitHub. [X]
3. **No real authentication.** Tenant context comes from a dev header in local/test only. Phase 2
   replaces it. Do not deploy publicly.
4. **`users` has no RLS.** By design (a user joins many orgs). Cross-tenant user enumeration is
   prevented by routing through the RLS-secured `memberships` join and by not exposing a user-list
   endpoint in Phase 1. Phase 2 must keep that invariant.
5. **Local Docker PostgreSQL is a superuser** that bypasses RLS, so RLS tests are only meaningful
   against Neon or against the `marketpulse_app` role created by the bootstrap script on any DB.
6. **Organization creation is not a public endpoint.** Provisioning is admin/bootstrap only
   (`TenantProvisioningService` + the bootstrap path). A future admin UI/signup is Phase 2+.
7. **Alembic autogenerate is not used.** The initial migration is hand-written to control RLS and
   grants precisely; future migrations may use autogenerate for table changes but must hand-write
   RLS/grant changes.

---

## 10. Evidence required before Phase 2

| # | Evidence | Command or place | Result to record |
|---|---|---|---|
| E1 | Unit tests on the owner's machine | `cd backend; uv run pytest` | `125 passed, 9 deselected` (paste the last line) |
| E2 | Migration against real Neon | `uv run alembic upgrade head` (with `MP_DATABASE_DIRECT_URL` set) | `Running upgrade -> 0001` with no error; tables visible in Neon |
| E3 | Two-tenant isolation + RLS bypass | `uv run pytest -m integration` (with both URLs + `MP_DB_APP_PASSWORD`) | `9 passed` (**not** `9 skipped`) |
| E4 | App role cannot bypass RLS | the `test_rls.py::test_app_role_has_no_bypassrls` line in E3 | PASS, `rolbypassrls = false` |
| E5 | (carried) Redis Cloud limits | Redis Cloud console | record in ADR-0020 (still provisional from Phase 0) |

Also record: the Neon region, the `marketpulse_app` role name used, and the first commit hash after
`git commit` (confirm `.env` was not in `git status`).

---

## 11. Gate decision

| Condition | State |
|---|---|
| Build list complete | Yes |
| Quality gate green in the authoring environment (unit + lint + format + mypy + offline migration SQL) | Yes [V-today] |
| Exit-gate DB items evidenced on the owner's machine | Pending E2–E4 [U]/[X] |
| Deviations recorded | Yes (ADR-0021..0024) |

**Recommendation:** treat Phase 1 as **passed conditionally**. Close E1–E4 (E5 carried from Phase
0), then declare the gate met. No Phase 2 work should start before that, per blueprint section 24.

---

## 12. Preview of Phase 2 (not started)

Per the blueprint roadmap: application shell and frontend foundations — React/TypeScript shell,
routing, design tokens, navigation, auth screens, workspace selector, reusable components, API
client, query cache, error/empty/loading states. Exit gate: authenticated shell works against the
API; responsive layout and keyboard navigation tested; no mock data appears as real data.

Known Phase 1 inputs for Phase 2:
- Replace the dev header resolver (`HeaderTenantContextResolver`, ADR-0024) with an auth-backed
  `TenantContextResolver` that reads an authenticated session. The port, the session dependency,
  and the use cases do not change.
- Build the login/session/cookie/CSRF flow on the existing `users` + `memberships` tables and the
  `core.security` Argon2id hasher. The `User` domain entity already omits `password_hash` by design.
- Expose member/invitation endpoints through the RLS-secured `memberships` join, preserving the
  invariant that `users` itself is never enumerated cross-tenant.

A detailed Phase 2 plan will be written from blueprint section 20 only after the gate is declared.

---

## 13. Glossary

| Term | Meaning here |
|---|---|
| GUC | PostgreSQL Grand Unified Configuration parameter; here `app.tenant_id` |
| `SET LOCAL` / `set_config(..., true)` | a setting scoped to the current transaction, reset at COMMIT |
| RLS | PostgreSQL row-level security; policies restrict which rows a role can see/modify |
| `NOBYPASSRLS` | a role attribute that prevents bypassing RLS (the app role has it) |
| Default-deny | with no tenant GUC set, RLS matches no rows, so nothing is returned |
| Port / adapter | a port is an interface the application needs; an adapter is the real code implementing it |
| Provisioning | the admin/bootstrap path that creates tenants/users (owner role, bypasses RLS) |

---

## 14. Revision history

### v2 hotfix (first real-database run)

The first end-to-end run against a live Neon database exposed a defect the offline
quality gate could not catch (integration tests require a real PostgreSQL):

- **Root cause.** The ORM models declared cross-table `ForeignKey` columns but no
  `relationship()`. SQLAlchemy's unit of work guarantees cross-mapper INSERT order
  only through `relationship()` definitions; bare FK columns order DDL, not flushes.
  `AuditEventORM` therefore flushed before `OrganizationORM`, and
  `test_two_tenants_are_isolated` failed with `ForeignKeyViolation` on
  `audit_events.organization_id` — the same failure would have hit
  `POST /organizations` on the API path.
- **Fix.** Added many-to-one `relationship(..., passive_deletes=True)` definitions to
  `AuditEventORM`, `MembershipORM` and `WorkspaceORM`, mirroring the existing FKs.
  Flush order is now organizations/users → memberships/workspaces/audit_events.
- **Test hardening.** `test_tenant_isolation._cleanup` now also deletes the probe
  user, making the test idempotent (a rerun previously died on the unique-email
  CONFLICT).
- **Verification.** `pytest -m integration`: 9 passed, run twice consecutively
  against live Neon; unit suite 125 passed; ruff/format/mypy strict all clean.
- **New tool.** `scripts/db/check_db_setup.py` — a setup doctor that validates `.env`
  syntax (catches the REDIS_URL=" wrapper and `<...>` placeholder mistakes), connects
  as both roles, probes CREATE/DROP on `public`, and pings Redis without ever
  printing a secret.
