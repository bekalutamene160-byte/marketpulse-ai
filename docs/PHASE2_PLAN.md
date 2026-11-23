# Phase 2 plan: application shell and frontend foundations

**Source of truth:** `MARKETPULSE_AI_SYSTEM_DESIGN.md` section 20, Phase 2. This plan is written
after the Phase 1 exit gate was declared met (9 integration tests passed twice against live Neon
on the owner's machine, unit suite green, dev org provisioned, API serving).

**Blueprint build list (section 20, Phase 2):**
React/TypeScript shell, routing, design tokens, sidebar/navigation, auth screens, workspace
selector, reusable table/card/form/status components, API client, query cache, error/empty/loading
states.

**Blueprint exit gate (section 20, Phase 2):**
authenticated shell works against API; responsive layout and keyboard navigation are tested; no
mock data appears as real data in customer screens.

**Phase 1 hand-over this phase must deliver** (PHASE1_REPORT section 12, ADR-0024,
`domain/entities.py` and `user.py` docstrings):
1. Replace the dev header resolver with an auth-backed `TenantContextResolver` (port unchanged).
2. Login/session/cookie/CSRF flow on `users` + `memberships` + the existing Argon2id hasher.
3. Member endpoints through the RLS-secured `memberships` join; `users` is never enumerated
   cross-tenant.
4. Self-service signup becomes possible (FR-001 "users can register"); organization creation
   moves from script-only to a real signup path behind rate limiting.

---

## Part A — Backend: the real authentication slice

### A1. Migration `0002_auth_sessions`

New table `auth_sessions` (user-scoped, like `users`; no RLS — there is no single tenant):

| column | type | notes |
|---|---|---|
| id | UUID | primary key |
| user_id | UUID | FK users(id) ON DELETE CASCADE, indexed |
| token_hash | VARCHAR(64) | SHA-256 hex of the opaque session token; UNIQUE; the raw token never touches the database |
| csrf_token_hash | VARCHAR(64) | SHA-256 hex of the CSRF token bound to this session |
| organization_id | UUID | nullable FK organizations(id) ON DELETE CASCADE — the active org (workspace selector) |
| created_at / last_seen_at / expires_at | TIMESTAMPTZ | absolute expiry, default lifetime 7 days |

Plus:
- A second permissive RLS policy on `memberships`:
  `memberships_user_access FOR SELECT USING (user_id::text = current_setting('app.user_id', true))`.
  Rationale: the workspace selector must list ALL of a signed-in user's memberships across
  organizations. The tenant policy alone hides other orgs even from the member. The user policy
  lets a session see exactly its own membership rows and nothing else; with no `app.user_id` GUC
  the policy matches nothing (default-deny preserved). This is ADR-0025/0026 territory and is
  tested by a live RLS test.
- Grants: `SELECT, INSERT, UPDATE, DELETE ON auth_sessions` to the app role (session lifecycle is
  app-owned). No `UPDATE ON users`: transparent Argon2id re-hash persistence is deferred —
  `needs_rehash()` is computed and logged, never written, so the app role keeps read-only access
  to the global `users` table.

### A2. Cookie and CSRF design

- `mp_session`: HttpOnly, SameSite=Lax, Path=/, Secure outside `local`, Max-Age = lifetime.
  The value is an opaque `secrets.token_urlsafe(32)`; only its SHA-256 is stored.
- `mp_csrf`: readable (NOT HttpOnly) so the SPA can echo it, SameSite=Lax. Bound to the session
  via `csrf_token_hash`.
- Every **authenticated** state change requires header `X-CSRF-Token` matching the `mp_csrf`
  cookie AND the session's stored hash. Login/register are additionally protected by the rate
  limiter; login-CSRF is documented as a Phase 15 hardening item.
- Dev same-site strategy: the Vite dev server proxies `/api/*` to the API, so the browser sees
  one origin and SameSite=Lax cookies work without CORS games. This mirrors the production
  reverse-proxy shape.

### A3. Endpoints (`/api/v1/auth`, plus one members read)

| Endpoint | Behavior |
|---|---|
| `POST /auth/register` | `{email, password, organization_name}` → creates user + organization (unique slug derived from the name) + owner membership + `General` workspace + audit rows, under the PRIVILEGED direct connection (the same provisioning path as Phase 1; RLS makes org creation impossible under the app role). Then creates the login session under the app role and sets cookies. 201. 409 on duplicate email/slug. 429 when rate-limited. 503 when no direct URL is configured. |
| `POST /auth/login` | `{email, password}` → Argon2id verify, user must be `active`; picks the first active membership as the default org; creates session; sets cookies; writes `auth.login_succeeded` audit. Uniform 401 for unknown email / wrong password / disabled user (no enumeration). 429 when rate-limited. |
| `POST /auth/logout` | Requires session + CSRF; deletes the session row, writes `auth.logout` audit, clears cookies. 204. |
| `GET /auth/me` | Session required. Returns the user, the active organization, and ALL of the user's memberships (the workspace-selector data) via the `app.user_id` policy. |
| `POST /auth/switch-organization` | `{organization_id}` + CSRF. Verifies an ACTIVE membership for this user (user policy), updates the session's active org. 403 when not a member. |
| `GET /organizations/members` | Tenant-scoped member list of the current org (join memberships→users for emails). Read-only; invitations are a later phase (no email adapter exists yet). |

### A4. New modules (exact files)

| File | Purpose |
|---|---|
| `core/cookies.py` | cookie/header name constants + pure helpers (no framework imports) |
| `core/ratelimit.py` | fixed-window in-process rate limiter, clock-injected, thread-safe |
| `domain/entities.py` | add `MemberSummary` (membership + email view) |
| `domain/audit.py` | add `AUTH_REGISTERED`, `AUTH_LOGIN_SUCCEEDED`, `AUTH_LOGOUT` |
| `application/ports/auth.py` | `PasswordHasher`, `TokenGenerator`, `CredentialReader`, `SessionStore` protocols |
| `application/ports/repositories.py` | add `MembershipReader.list_for_user(user_id)` + member-view read |
| `application/services/auth.py` | `AuthenticationService`: register/login/logout/me/switch |
| `infrastructure/db/models/auth_session.py` | `AuthSessionORM` (+ relationships per the Phase 1 hotfix lesson) |
| `infrastructure/db/auth.py` | SQLAlchemy adapters: credential reader, session store, membership-by-user reader |
| `infrastructure/db/repositories.py` | `list_members_with_users` implementation |
| `infrastructure/tenancy/session_resolver.py` | `SessionTenantContextResolver` (cookie → context or None) |
| `api/v1/schemas/auth.py` | request/response models |
| `api/v1/routers/auth.py`, `api/v1/routers/members.py` | endpoints (sync `def`, ADR-0021) |
| `api/deps.py` | `get_plain_db_session` (no tenant GUC), `get_priv_db_manager`, `get_auth_service`, `get_rate_limiter` |
| `main.py` | wire `priv_db_manager` (direct URL), session resolver, rate limiter |
| `config.py` | `session_lifetime_hours`, `auth_rate_limit_attempts`, `auth_rate_limit_window_seconds` |
| `migrations/versions/0002_auth_sessions.py` | table + policy + grants |
| `scripts/db/make_dev_org.py` | unchanged (still useful for seeding) |

The dev header resolver is NOT deleted: it stays for `local`/`test` with the explicit opt-in flag
(ADR-0024 remains valid for tooling); the composition root now prefers the session resolver when a
database is configured, and the header resolver only when the dev flag is on. Production keeps
failing closed.

### A5. Backend tests

- `tests/unit/test_auth_service.py` — register/login/logout/me/switch with fakes; uniform 401s;
  disabled user; slug uniqueness; rate limiting (fake clock).
- `tests/unit/test_auth_api.py` — TestClient: cookie flags, CSRF enforcement (403 without header),
  register→me round trip with injected fakes, 401/409/429 envelopes.
- `tests/unit/test_session_resolver.py` — cookie parsing, expired session, disabled user → None.
- `tests/unit/test_ratelimit.py` — window behavior.
- `tests/unit/test_migrations.py` — extend for 0002 (table exists, user-access policy, grants).
- `tests/integration/test_auth_live.py` — real Neon: register via the service against both DSNs,
  resolver resolves, tenant-scoped reads work, memberships-by-user works under RLS, logout
  revokes, cross-tenant switch denied. Cleanup deletes seeded rows (idempotent reruns).

## Part B — Frontend: the application shell

Stack additions (already blueprint-approved in section 6): `react-router-dom` (routing),
`@tanstack/react-query` (server state/cache), `react-hook-form` + `zod` (typed forms).

```
frontend/src/
  styles/tokens.css        design tokens: dark-navy foundation, gold accent, spacing, radius,
                           focus ring, status colors (blueprint 13.10)
  styles/base.css          reset, focus-visible, skip-link, reduced-motion respect
  lib/api.ts               typed client: relative /api paths, credentials, CSRF header,
                           error-envelope parsing -> ApiError{code,message,requestId,status}
  lib/auth.ts              session/CSRF cookie helpers + login/register/logout/me/switch calls
  app/providers.tsx        QueryClientProvider (sensible retry/staleTime, no retry on 4xx)
  app/router.tsx           routes: /login /register protected(/ /members /status) 404
  app/AppShell.tsx         sidebar + topbar, org selector, user menu, skip link, <Outlet/>
  components/ui/           Button, TextField, Card, StatusBadge, Alert, Spinner, EmptyState,
                           ErrorState, PageHeader, DataTable (accessible table)
  features/auth/           LoginPage, RegisterPage, ProtectedRoute, useSession hooks
  features/overview/       OverviewPage (real current-org card + real workspaces table)
  features/members/        MembersPage (real member list via the RLS-secured join)
  features/status/         StatusPage (the Phase 0 health page, preserved as a route)
```

Every data view implements loading skeleton, empty, error and success states from REAL endpoints
only — there is no mock data in any customer screen. The shell is responsive (sidebar collapses to
a top-bar menu under 768px, `aria-expanded` + Escape-to-close) and keyboard accessible (skip link,
visible focus rings, semantic landmarks, labelled controls).

Frontend tests (vitest + testing-library): login/register form flows + error surfaces, protected
route redirect, shell keyboard navigation and responsive toggle, members/overview loading-empty-
error-data states, API client envelope parsing and CSRF header attachment.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Cookie never arrives in browser dev (cross-site) | Vite proxy makes dev same-origin; cookie is SameSite=Lax |
| RLS blocks the org selector | second per-user policy (`app.user_id`), live-tested default-deny when unset |
| Rate limiter accuracy behind proxies | keyed by client IP; single-process Phase 2 scope, documented |
| Registration under RLS | uses the privileged provisioning path exactly as Phase 1 designed (ADR-0023) |
| Architecture test breaks | auth service depends only on ports; resolver is an adapter |
| Frontend strict tsconfig / eslint strictTypeChecked | code written to strict rules, verified by running all four gates |

## Verification (the phase gate)

Backend: `uv run pytest` (unit), `uv run pytest -m integration` (live Neon, `9+ passed` not
skipped), `ruff check`, `ruff format --check`, `mypy` strict. Frontend: `npm run lint`,
`npm run typecheck`, `npm test`, `npm run build`. Then the owner-run walkthrough: register →
shell loads with real org data → switch org → members list → logout → login again.
