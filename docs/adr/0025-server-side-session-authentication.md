# ADR 0025: Server-side session authentication with digest-stored cookies

- Status: accepted
- Date: 2026-11-21
- Blueprint reference: 15.1 (authentication), 14.1 (auth routes), 14.2 (rate limiting), 18.1 (error codes)
- Supersedes the provisional part of ADR-0024 (the dev header resolver is no longer the default)

## Context

Phase 2 needs real sign-in. The application role is `NOBYPASSRLS` and RLS is
default-deny, so authentication must produce a server-verifiable identity per
request without trusting the client, and it must work with Neon's PgBouncer
transaction pooling (no session-level state) and with a plain React SPA.

## Decision

1. **Opaque server-side sessions, not JWTs.** Login creates a row in
   `auth_sessions` (migration 0002). The browser holds an opaque
   `secrets.token_urlsafe(32)` value in an HttpOnly, SameSite=Lax cookie; ONLY the
   SHA-256 digest of the token is stored. A stolen database dump cannot be
   replayed as a login, revocation is a DELETE, and there is no signature secret
   to rotate. JWTs were rejected: revocation lists, rotation and claims plumbing
   buy nothing for a monolith with server-side sessions.
2. **CSRF binding.** A second random value lives in a readable `mp_csrf` cookie and
   as a digest in the session row. Every authenticated state change must present
   `X-CSRF-Token` matching the cookie AND the stored digest (constant-time
   compare). Reads need no CSRF header.
3. **SameSite=Lax + same-origin dev proxy.** The Vite dev server proxies `/api` to
   the API so the browser sees one origin — cookies just work, matching the
   production reverse-proxy shape. No CORS-credential dance in development.
4. **Uniform authentication failures.** Unknown email, wrong password and disabled
   accounts return the SAME 401 message. Membership absence after a valid login is
   authorization, not authentication: 403.
5. **Rate limiting at the door.** A fixed-window in-process limiter (clock
   injected, thread-safe) caps login and register per client IP (10 / 300 s by
   default, `MP_AUTH_RATE_LIMIT_*`). Exact for the single-process Phase 2 shape;
   moves to shared Redis when Phase 5 introduces it.
6. **No UPDATE grant on users.** Transparent Argon2id re-hash persistence is
   deferred: `needs_rehash()` is computed and logged, never written, so the app
   role keeps read-only access to the global identity table.
7. **Register commits in order.** Signup runs on the PRIVILEGED direct connection
   (ADR-0023: RLS makes app-role org creation impossible) and commits BEFORE the
   session row is created on the app role — a FK cannot see an uncommitted row
   from another transaction, so ordering is a correctness requirement, not a style
   choice.
8. **Login/logout are structured logs, not audit rows.** `audit_events` is
   tenant-scoped (RLS WITH CHECK needs `app.tenant_id`); a login has no tenant
   until the default organization is chosen. Tenant audit history for auth events
   arrives with the observability phase. Registration writes the normal tenant
   audit rows via the reused provisioning services.

## Alternatives considered

- **JWT access tokens:** rejected (see above) — revocation and secret rotation
  complexity for no benefit at this scale.
- **Password re-hash persistence now:** rejected — would require UPDATE on the
  global `users` table for a path that cannot trigger until hash parameters are
  deliberately raised.
- **Cookie without CSRF token (SameSite-only):** rejected — Lax already blocks
  cross-site POSTs in modern browsers, but the explicit token keeps the guarantee
  under old browsers and future cross-site deployments.
- **Email verification / password reset:** deferred — FR-001 recovery flows need an
  email adapter (ADR-012); recorded as a known gap, not silently dropped.

## Consequences

- Tenant context for every API request now flows from the session:
  cookie → `auth_sessions` (digest lookup, expiry-checked) → active user →
  `TenantContext(active_org, user)`, through the SAME `TenantContextResolver` port
  the dev header used. Use cases, repositories and the session dependency did not
  change (the Phase 1 hand-over promise kept).
- The workspace selector is powered by two new per-user RLS policies (ADR-0026).
- Sessions die with their organization (FK CASCADE) — deleting a tenant revokes
  its sessions immediately.
- Known gaps (documented, deliberate): email verification and password reset
  (needs email adapter), shared rate-limit counters (Phase 5), login-CSRF
  hardening (Phase 15), session GC beyond per-user opportunistic deletes.

## Verification

- `tests/unit/test_auth_service.py` (18), `tests/unit/test_auth_api.py` (9),
  `tests/unit/test_session_resolver.py` (3), `tests/unit/test_ratelimit.py` (4),
  migration/model/config test extensions.
- `tests/integration/test_auth_live.py` against live Neon: signup → login →
  resolver → tenant reads → per-user policies → default-deny → switch → logout.
- `scripts/e2e_auth_smoke.py`: the real `create_app` over HTTP against live Neon:
  register 201 → me 200 → tenant read 200 → members 200 → logout 204 → me 401 →
  wrong password uniform 401.
