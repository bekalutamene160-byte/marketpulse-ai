# Threat model

Source: blueprint section 15 (security, privacy, trust) and 19.4 (environments). This is a living
document: each phase adds the threats it introduces and ticks off the mitigations it delivers.
Status values: **done** (implemented and tested), **planned: Phase N**, **accepted risk**.

## Assets
1. Customer business data (prices, products, competitor lists) and its tenant boundaries.
2. Credentials: database and Redis URLs, later integration credentials and LLM keys.
3. Evidence integrity: every number must trace back to a stored source observation.
4. Availability of the core product when an external dependency (LLM, source site) is down.

## Trust boundaries
Browser <-> API. API <-> PostgreSQL. API/worker <-> Redis. Worker <-> public websites (untrusted).
API/worker <-> LLM provider (later). Developer machine <-> cloud services (now).

## Threats and mitigations

| # | Threat | Where | Mitigation | Status |
|---|--------|-------|------------|--------|
| T1 | Secret committed to git | repo | `.env` git-ignored, `.env.example` placeholders only, `pre-commit` private-key check, CI secret scan | done (gitignore, example, hook); CI scan: planned Phase 15 |
| T2 | Secret leaks through logs, errors or repr | config, logging | URLs are `SecretStr`; validation errors hide input; health output is coarse; tests assert no leak | done |
| T3 | Misconfigured production starts silently with insecure defaults | config | fail closed: production/staging require PostgreSQL with TLS, no wildcard CORS, production needs TLS Redis, dev tenant header forbidden in non-local | done |
| T4 | Log injection through `X-Request-ID` | middleware | only `[A-Za-z0-9_-]{8,64}` accepted, otherwise a fresh UUID | done |
| T5 | Information disclosure through error pages | API | one error envelope, internal diagnostics logged not returned, 500s generic, validation errors do not echo input | done |
| T6 | Public health endpoint reveals internals or wakes the database | API | `/health/live` touches nothing; `/health/ready` returns states and timings only, no hostnames or exception text | done |
| T7 | API surface advertised in production | API | docs and OpenAPI disabled in production | done |
| T8 | Cross-tenant data access | database | `organization_id` predicate in every repository PLUS PostgreSQL RLS with `USING`+`WITH CHECK`; two-tenant integration test; default-deny when tenant GUC unset | done (Phase 1) |
| T9 | **Neon default roles bypass RLS** | database | separate `marketpulse_app` role created by bootstrap script with `NOBYPASSRLS`; integration test asserts `rolbypassrls = false` | done (Phase 1) |
| T10 | Tenant context leaks across pooled connections | database | `set_config(..., true)` transaction-local (SET LOCAL), reset at COMMIT; migrations use the DIRECT URL; app role on the POOLED URL | done (Phase 1) |
| T11 | Duplicate or lost background work | queue | transactional outbox, idempotent tasks, Redis holds no business state | planned: Phase 5 |
| T12 | SSRF through user-supplied URLs | collectors | validate URL, DNS, resolved IP, every redirect and browser navigation; block internal and metadata ranges | planned: Phase 6 |
| T13 | Prompt injection from scraped page text, CSV cells, reviews | agent | untrusted content kept outside instructions, tool allow-list, evidence-cited answers | planned: Phase 12 |
| T14 | Vulnerable dependency | supply chain | lockfiles committed, `pip-audit` and `npm audit` in CI | done (lockfiles, CI jobs written; CI not yet executed) |
| T15 | Browser JavaScript reads a secret | frontend | only `VITE_*` variables reach the browser and are documented as public; no secrets in frontend source | done |
| T16 | Client-supplied tenant id trusted in production | API, tenancy | tenant context resolved server-side from the session (ADR-0025); the dev header stays a local/test-only opt-in (ADR-0024) | done (Phase 2) |
| T17 | Session token theft / database leak replay | auth | opaque token, HttpOnly + SameSite=Lax + Secure outside local; only the SHA-256 digest stored; absolute expiry; logout deletes; org deletion cascades sessions (ADR-0025) | done (Phase 2) |
| T18 | CSRF on authenticated state changes | auth | CSRF token digest-bound to the session, echoed via `X-CSRF-Token`; SameSite=Lax; login-CSRF hardening deferred to Phase 15 | done (Phase 2) |
| T19 | Brute-force sign-in / signup abuse | auth | fixed-window per-IP rate limiter (10 / 300 s default); uniform 401 (no user enumeration); in-process counters move to shared Redis in Phase 5 | done (Phase 2, single-instance) |

## Accepted risks (Phase 2)
- Development uses free-tier cloud services over the public internet. Credentials are scoped to a
  development project containing no real customer data. Never point a local `.env` at production.
- The rate limiter is in-process: exact for one API instance, per-replica behind several until
  Phase 5 moves counters to shared Redis.
- Email verification and password reset do not exist yet (need the email adapter, ADR-012):
  do not onboard real users who cannot reach the operator to reset a password.
- Password hashes are never re-persisted after parameter changes (no UPDATE grant on users,
  ADR-0025); re-hash triggers only if the pinned Argon2id constants are deliberately raised.
- `docker-compose.yml` uses a throwaway password; the local PostgreSQL user is a superuser that
  bypasses RLS, so RLS tests are only meaningful against the cloud (or a role created by the
  bootstrap script).
- The integration tests (migration, two-tenant isolation, RLS bypass) require a real PostgreSQL;
  they are opt-in (`-m integration`) and skip when no URL is configured.

## Review rule
Any change that adds an endpoint, a credential, a queue message, or an outbound network call must
update this table in the same pull request.
