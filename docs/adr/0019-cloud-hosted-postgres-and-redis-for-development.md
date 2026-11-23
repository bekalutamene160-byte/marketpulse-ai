# ADR 0019: Cloud-hosted PostgreSQL and Redis for development instead of local Docker

- Status: accepted (deviation from blueprint section 19.1)
- Date: 2026-11-20
- Blueprint reference: 19.1 (local development), 19.4 (environments), 19.5 (cost and free-tier reality), ADR-002

## Context
Blueprint 19.1 prescribes Docker Compose with local PostgreSQL and Redis. The developer's laptop
cannot run Docker, PostgreSQL and Redis together. Blueprint 19.1 itself says to keep load low on
this laptop. ADR-002 still requires PostgreSQL from the first slice, so SQLite is not an option.

## Decision
For development, use managed cloud services instead of local containers:
- PostgreSQL: Neon (free plan).
- Redis (Dramatiq broker): see ADR-0020.

`docker-compose.yml` stays in the repository as an optional, equivalent local stack for any machine
that can run it, and for CI-style parity. Nothing in application code knows which one is used: the
only difference is the value of `MP_DATABASE_URL` and `MP_REDIS_URL`.

## Alternatives considered
- SQLite for development: rejected. It violates ADR-002 and cannot exercise row-level security,
  which Phase 1 depends on.
- Local PostgreSQL and Redis installed natively on Windows: not chosen. Still heavy on the target
  laptop, and diverges from the production topology.
- Cloud development environment (for example GitHub Codespaces): kept as a fallback, not verified.

## Consequences
- Verified facts about Neon Free (neon.com, checked 2026-11-20): 1 GB storage per project, 100
  compute hours per project per month, scale-to-zero after 5 minutes of inactivity that cannot be
  disabled on the free plan. Plan limits change; blueprint 19.5 says not to depend on them.
- First connection after idle is slow (cold start). Hence `probe_timeout_seconds` defaults to 10s,
  and `/health/live` never touches the database so platform pings cannot wake it or burn compute
  hours. Only `/health/ready` does, and it should be polled sparingly.
- Development needs internet access. Offline work uses the unit test suite, which needs no services.
- Phase 1 risk, to be checked then: Neon's default roles may bypass row-level security. The
  application must connect as a role created with plain SQL where `rolbypassrls` is false, and a
  test must assert it (blueprint Phase 1 exit gate: "DB role cannot bypass RLS").
- Neon pooled connections run PgBouncer in transaction mode: tenant context must use `SET LOCAL`
  inside a transaction (blueprint 7.6), and migrations must use the direct, non-pooled URL.

## Verification
`uv run pytest -m integration` connects to the real services and passes. See docs/DEPLOYMENT.md.
