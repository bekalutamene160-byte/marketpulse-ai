# ADR 0023: Least-privilege application DB role created by a bootstrap script

- Status: accepted
- Date: 2026-11-20
- Blueprint reference: 7.6 (RLS), 15.7 (least-privilege DB roles), 19.1 (local development)

## Context
Phase 0 research found that Neon's default project roles may bypass row-level security (threat
T9). If the application connected as such a role, RLS would be silently ineffective. The
application also must not own the tables: an owner bypasses RLS by default. And migrations must
run against the DIRECT (non-pooled) connection, because PgBouncer transaction mode on the pooled
endpoint breaks DDL and session-level `SET` (ADR-0022).

## Decision
Use two distinct database roles and connections:

1. **Owner role** (the Neon project owner, or the local superuser): connects via the DIRECT
   `MP_DATABASE_DIRECT_URL`. Used only by Alembic migrations and the provisioning/bootstrap path.
   It owns the tables and bypasses RLS for admin work.
2. **Application role** `marketpulse_app` (configurable via `MP_DB_APP_ROLE`): connects via the
   POOLED `MP_DATABASE_URL`. Used by the API and worker at runtime. It owns no tables, has
   `NOBYPASSRLS`, and receives only the `GRANT`s the migration issues (SELECT on organizations,
   memberships, users; SELECT/INSERT/UPDATE on workspaces; SELECT/INSERT on audit_events).

The application role is created once by `backend/scripts/db/bootstrap_app_role.py`, run by the
developer against the direct URL before the first migration. The script is idempotent, composes
the role name and password with `psycopg.sql` identifiers/literals (never f-strings), and
re-asserts `rolbypassrls = false`, failing closed if it is ever true. The migration assumes the
role exists and GRANTs it privileges; it does not create the role (role lifecycle is a DBA/cloud
concern, schema is an application concern).

## Alternatives considered
- **Run the app as the Neon default role:** rejected. It may bypass RLS (T9), defeating the
  entire tenant-isolation design.
- **Create the role inside the Alembic migration:** rejected. A password would have to live in
  the migration SQL or be read from the environment mid-migration, coupling role lifecycle to
  schema evolution and making the migration non-deterministic across environments.
- **`FORCE ROW LEVEL SECURITY` instead of a separate role:** rejected (see ADR-0022).

## Consequences
- Developer setup adds one step before the first migration: run `bootstrap_app_role.py`. Documented
  in `docs/DEPLOYMENT.md`.
- The application role's privileges are least-privilege by construction: even with a stolen
  credential, an attacker cannot drop tables or read across tenants (RLS).
- The migration GRANTs reference the role by name, validated to a safe identifier regex before
  interpolation, so a misconfigured `MP_DB_APP_ROLE` cannot inject SQL.

## Verification
`tests/integration/test_rls.py::test_app_role_has_no_bypassrls` asserts `rolbypassrls = false`
for the connected role. `tests/unit/test_migrations.py` asserts the GRANTs target the configured
role. `bootstrap_app_role.py` re-asserts the property after creation.
