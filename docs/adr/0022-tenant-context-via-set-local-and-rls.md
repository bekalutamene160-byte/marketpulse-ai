# ADR 0022: Tenant context via transaction-local GUCs and row-level security

- Status: accepted
- Date: 2026-11-20
- Blueprint reference: 7.6 (PostgreSQL tenant isolation), 15.4 (tenant isolation), 7.4 (audit_events)

## Context
The product is multi-tenant. A bug that lets tenant A read tenant B's data is the worst failure
mode. Blueprint 7.6 requires two defenses: an application-layer tenant filter on every repository
call, AND PostgreSQL row-level security as defense in depth. Phase 0 research (ADR-0019) found
two Neon-specific hazards: default roles may bypass RLS (threat T9), and the pooled endpoint runs
PgBouncer in transaction mode, so a session-level `SET` would leak the tenant across reused
server-side connections (threat T10).

## Decision
Set the tenant identity with `SELECT set_config('app.tenant_id', :tid, true)` — equivalent to
`SET LOCAL` — as the first statement inside each request's transaction. The `true` argument
makes the setting transaction-local: it is reset at COMMIT/ROLLBACK, so it cannot leak across
pooled connections. The tenant id is passed as a bound parameter, never string-interpolated, so
there is no injection surface.

Enable RLS on every tenant-scoped table (`organizations`, `memberships`, `workspaces`,
`audit_events`) with a policy `USING (organization_id::text = current_setting('app.tenant_id',
true)) WITH CHECK (...)`. The `true` second argument to `current_setting` returns NULL when the
GUC is unset, so the comparison is NULL and matches nothing: the system is **default-deny** until
a tenant is explicitly established. `users` is global and has no RLS; access to it is mediated
through the RLS-secured `memberships` join.

The application role owns no tables and has `NOBYPASSRLS` (ADR-0023), so RLS is enforced against
it. The table owner bypasses RLS for provisioning and migrations.

## Alternatives considered
- **Session-level `SET` (not LOCAL):** rejected. Under PgBouncer transaction mode it leaks to the
  next tenant (T10).
- **Application filter only, no RLS:** rejected. A single missed `WHERE organization_id = ?`
  crosses tenants. RLS is the guarantee that survives a repository bug.
- **`FORCE ROW LEVEL SECURITY`:** not used. It would also subject the table owner to RLS, which
  varies by provider and could block provisioning. The owner bypassing RLS is acceptable (it is
  the admin role); the application role is the one that must not bypass, and that is asserted.

## Consequences
- Every tenant-scoped request must run inside a transaction (the dependency opens one) and set
  the GUC before any query. The dependency `get_db_session` guarantees this ordering.
- Tenant filtering happens twice: the explicit predicate in the repository AND RLS. Either alone
  is a defense.
- Default-deny means a job or request that forgets to set the context sees nothing, never
  another tenant's data.

## Verification
`tests/unit/test_migrations.py` asserts RLS is enabled and policies use `current_setting(...,
true)` with `WITH CHECK`. `tests/integration/test_rls.py` asserts `rolbypassrls = false` and
default-deny. `tests/integration/test_tenant_isolation.py` proves two tenants cannot see each
other's rows.
