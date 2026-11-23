# ADR 0024: Dev/test header tenant resolver (provisional, replaced by Phase 2 auth)

- Status: superseded as the DEFAULT by Phase 2 authentication (ADR-0025); still
  accepted as a local/test tooling option behind MP_ENABLE_DEV_TENANT_HEADER
- Date: 2026-11-20
- Blueprint reference: 15.1 (authentication), 15.4 (tenant isolation), 14.1 (auth routes)

## Context
Phase 1 builds the tenant-context mechanism, RLS, and the data model — but authentication (login,
sessions, cookies) is Phase 2. To exercise the tenant-isolation machinery end to end now (the
exit gate requires "unauthorized access returns correct errors" and two-tenant isolation tests),
there must be SOME source of the tenant identity for a request. It cannot be a client-supplied
`organization_id` trusted blindly in production, because that is exactly the cross-tenant bug
RLS exists to prevent.

## Decision
Provide a `HeaderTenantContextResolver` that reads `X-MP-Organization` (and optional
`X-MP-User`, `X-MP-Workspace`) headers, validates them as canonical UUIDs, and returns a
`TenantContext`. Wire it ONLY in `local` and `test` environments, gated by
`MP_ENABLE_DEV_TENANT_HEADER`. `Settings._non_local_guardrails` rejects
`enable_dev_tenant_header=true` in `staging`/`production`, so the app refuses to start with it
on where real tenants exist. In non-local environments the default resolver is `None` and every
tenant-scoped endpoint fails closed with 401 until Phase 2 ships an auth-backed resolver.

A malformed or missing header resolves to `None`, which `TenantContextService` turns into 401
UNAUTHORIZED — uniform failure, no information about which header was wrong.

## Alternatives considered
- **Trust a client `organization_id` query/body parameter in production:** rejected. It is the
  cross-tenant vulnerability itself.
- **No resolver until Phase 2:** rejected. It would leave the Phase 1 exit gate
  (unauthorized-access errors, two-tenant isolation) untestable end to end.
- **A real password-login flow now:** rejected as scope creep. Phase 2 is the auth phase.

## Consequences
- Phase 1 can demonstrate the full tenant flow (header -> context -> SET LOCAL -> RLS -> 401 on
  missing context) in tests and local development.
- The resolver is an adapter behind the `TenantContextResolver` port. Phase 2 replaces it with an
  auth-backed resolver (reading an authenticated session, not headers) without touching use
  cases, repositories, or the session dependency.
- Until Phase 2, the app MUST NOT be deployed where real tenants exist: there is no real
  authentication.

## Verification
`tests/unit/test_tenancy.py` covers the header resolver and the 401 paths.
`tests/unit/test_tenant_api.py` proves 401 without context and 200 with a valid UUID header.
`Settings` rejects the flag in staging/production (`tests/unit/test_config.py`).
