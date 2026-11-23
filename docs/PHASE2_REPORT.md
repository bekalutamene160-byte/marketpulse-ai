# MarketPulse AI: Phase 2 Report

**Phase:** 2 of 16, "Application shell and frontend foundations" (blueprint section 20)
**Report date:** 2026-11-21
**Source of truth:** `MARKETPULSE_AI_SYSTEM_DESIGN.md`
**Status:** Phase 2 built and verified in the authoring environment AND against the owner's live
Neon database. Every claim below is tagged: **[V-today]** re-run for this report, **[V-live]**
executed against live Neon in the authoring sandbox (same database the owner uses), **[U]** to be
re-confirmed by the owner on their machine.

---

## 1. Scope: what Phase 2 required

From blueprint section 20.

**Build:** React/TypeScript shell, routing, design tokens, sidebar/navigation, auth screens,
workspace selector, reusable table/card/form/status components, API client, query cache,
error/empty/loading states.

**Exit gate:** authenticated shell works against API; responsive layout and keyboard navigation are
tested; no mock data appears as real data in customer screens.

**Phase 1 hand-over delivered** (PHASE1_REPORT section 12, ADR-0024): auth-backed tenant resolver
(same port, dev header demoted to a local/test opt-in), login/session/cookie/CSRF on `users` +
`memberships` + the existing Argon2id hasher, member endpoints through the RLS-secured join, and
self-service signup (FR-001).

---

## 2. Executive summary

- **Real authentication is live.** `POST /auth/register|login|logout`, `GET /auth/me`,
  `POST /auth/switch-organization`: opaque session token in an HttpOnly SameSite cookie, only its
  SHA-256 stored; CSRF token digest-bound to the session; per-IP fixed-window rate limiting;
  uniform 401s (no user enumeration); Argon2id verification with the Phase 1 hasher. ADR-0025.
- **Tenant isolation was extended, not weakened.** Two SELECT-only per-user RLS policies (ADR-0026)
  let a signed-in user see their own memberships across organizations and the names of those
  organizations — exactly what the workspace selector needs. Default-deny with no GUC is proven by
  a live test. The Phase 1 two-tenant isolation suite passes unchanged.
- **The shell exists and works against real data only.** React 19 + Vite + Tailwind 4 design tokens
  (dark navy / gold per blueprint 13.10), react-router routes, TanStack Query cache, typed API
  client with the stable error envelope, sidebar shell with organization selector and sign-out,
  Overview (real org + real workspaces), Members (real RLS-secured list), System status (real
  health endpoints). Loading, empty, error and success states everywhere; no mock data.
- **Quality gate [V-today, V-live]:** backend 168 unit tests + 10 integration tests passed twice
  consecutively against live Neon; ruff clean; formatter clean; mypy strict clean (71 source
  files). Frontend: eslint clean, `tsc -b --noEmit` strict clean, 22 vitest tests pass, production
  build succeeds. A full HTTP smoke through the real `create_app` against live Neon (register → me
  → tenant read → members → logout → revocation → uniform 401) passed and cleaned up after itself.

---

## 3. Exit-gate scorecard

| Gate item | Evidence | Status |
|---|---|---|
| Authenticated shell works against API | Full HTTP smoke vs live Neon [V-live]; owner walkthrough pending [U] | PASS (authoring) |
| Responsive layout tested | Sidebar → top-bar menu under 768px; `aria-expanded` + Escape-to-close covered in `AppShell.test.tsx` [V-today] | PASS |
| Keyboard navigation tested | Skip link is first tab stop; focus management on menu close; semantic landmarks; visible gold focus rings — all asserted in tests [V-today] | PASS |
| No mock data in customer screens | Every view renders only API-backed state; loading/empty/error are explicit [V-today, code review] | PASS |

---

## 4. What was built, and why

### 4.1 Backend (the auth slice Phase 1 handed over)

| Decision | Reason |
|---|---|
| Opaque server-side sessions, not JWTs | Revocation is a DELETE; a DB leak cannot be replayed (only digests stored); no signing secret to rotate (ADR-0025) |
| `auth_sessions` has NO row-level security | Sessions belong to a user (global identity), like `users`; the optional `organization_id` is the active-org pointer with ON DELETE CASCADE |
| Per-user RLS policies (ADR-0026) | The selector needs cross-tenant reads; two narrow SELECT policies preserve default-deny instead of granting bypass |
| Signup on the privileged connection | RLS makes app-role org creation impossible (ADR-0023); commits BEFORE the session row — a FK cannot see an uncommitted row from another transaction |
| Login/logout are logs, not audit rows | `audit_events` is tenant-scoped; a login has no tenant until the default org is chosen |
| No `UPDATE ON users` grant | Transparent Argon2id re-hash deferred; the app role keeps read-only access to global identity |
| Uniform 401 + 429 RATE_LIMITED | No user enumeration; sign-in/sign-up brute force capped per IP (in-process until Phase 5) |

New files: `core/cookies.py`, `core/ratelimit.py`, `application/ports/auth.py`,
`application/services/auth.py`, `application/services/signup.py`,
`infrastructure/db/models/auth_session.py`, `infrastructure/db/auth.py`,
`infrastructure/tenancy/session_resolver.py`, `api/v1/schemas/auth.py`,
`api/v1/routers/auth.py`, `api/v1/routers/members.py`,
`migrations/versions/0002_auth_sessions.py`. Extended: `deps.py`, `main.py`, `config.py`,
`router.py`, repositories and ports (per-user reads, member views, `list_by_ids`).

### 4.2 Frontend (the blueprint's Phase 2 build list, item by item)

| Blueprint item | Where |
|---|---|
| React/TypeScript shell | `app/AppShell.tsx` (sidebar, top-bar mobile menu, skip link, landmarks) |
| Routing | `app/router.tsx` (public /login /register; protected /, /members, /status; catch-all) |
| Design tokens | `styles/app.css` (`@theme`: navy/gold/ink/status scales; focus rings; reduced motion) |
| Auth screens | `features/auth/LoginPage.tsx`, `RegisterPage.tsx` (react-hook-form + zod; server envelope errors) |
| Workspace selector | Sidebar `<select>` fed by `/auth/me` memberships; `useSwitchOrganization` invalidates all cached queries |
| Reusable components | `components/ui/Controls.tsx` (Button, TextField), `Feedback.tsx` (Card, PageHeader, StatusBadge, EmptyState, ErrorState), `Spinner.tsx` |
| API client | `lib/api.ts` (relative paths via the Vite proxy, credentials, CSRF header, envelope → `ApiError`) |
| Query cache | TanStack Query: no retry on 4xx, one retry on transient failures, invalidation on mutations |
| Error/empty/loading states | Every page renders all of them from real endpoints |
| Status page | `features/status/StatusPage.tsx` — the Phase 0 health page preserved as a route |

**Dev same-origin strategy:** the Vite dev server proxies `/api` to the API, so the session cookie
(SameSite=Lax) works in the browser without CORS or HTTPS games — the same shape as the production
reverse proxy (blueprint 19.2).

---

## 5. Test evidence

### 5.1 Backend [V-today, V-live]

| Suite | Result |
|---|---|
| `uv run pytest` (unit) | **168 passed** (was 125; Phase 2 adds 43: auth service 18, auth API 9, resolver 3, rate limit 4, migration +5, models +2, config +2) |
| `uv run pytest -m integration` (live Neon + Redis) | **10 passed, twice consecutively** (9 Phase 1 tests unchanged + `test_auth_live.py`) |
| `ruff check` / `ruff format --check` | clean |
| `mypy` (strict, pydantic plugin) | no issues in 71 source files |
| `scripts/e2e_auth_smoke.py` (real `create_app` over HTTP vs Neon) | PASSED: register 201 → me 200 → tenant read 200 → members 200 → login 200 → logout 204 → me 401 → wrong password 401; cleanup verified |

`test_auth_live.py` proves on real Neon: signup via the privileged path, session creation under the
app role, cookie → resolver → tenant context, tenant-scoped reads, the per-user membership list
growing with a second org, both organization rows readable for the selector, **zero rows with no
GUC (default-deny)**, membership-guarded organization switching, CSRF-bound logout, revocation, and
garbage-cookie rejection. Cleanup deletes seeded rows; reruns are idempotent.

### 5.2 Frontend [V-today]

| Check | Result |
|---|---|
| `npm run lint` (eslint strictTypeChecked) | clean |
| `npm run typecheck` (`tsc -b --noEmit`, strict + exactOptionalPropertyTypes) | clean |
| `npm test` (vitest + testing-library, jsdom) | **22 passed** in 4 files |
| `npm run build` (tsc + vite) | succeeds (485 kB JS / 14.8 kB CSS, gzip 150 kB) |

Test coverage maps to the gate: login/register validation + server error surfaces + success
redirects (9), protected-route redirect and spinner (4), shell keyboard navigation and responsive
menu semantics incl. Escape + aria-expanded + org selector (5), members loading/error/data states
(3), API client envelope parsing, CSRF header attachment, credentials and network failure handling
(5).

### 5.3 What the tests do not cover

- No real-browser (Playwright) run yet: responsive behavior is tested at the behavior level
  (menu state, aria attributes) in jsdom; a pixel-level browser pass is Phase 13/15 polish.
- Email verification, password reset, and invitations do not exist (need the email adapter,
  ADR-012) — recorded gaps, not silent omissions.
- The rate limiter is single-instance; multi-replica behavior is a Phase 5 concern.

---

## 6. Deviations from the blueprint

| ID | Deviation | Reason | Status |
|---|---|---|---|
| ADR-0025 | Server-side cookie sessions instead of any JWT/token scheme | Revocation, digest storage, no rotation secret; fits monolith + PgBouncer | accepted |
| ADR-0026 | Two per-user SELECT RLS policies | Workspace selector needs cross-tenant reads without weakening default-deny | accepted |
| ADR-0024 | Dev header resolver demoted to local/test opt-in (no longer the default) | Replaced by the session resolver as designed | superseded (default) |
| note | Tailwind 4 with `@theme` tokens instead of a UI kit | Blueprint lists Tailwind + accessible primitives; tokens are code-owned | accepted |
| note | Self-service signup included (blueprint FR-001 + Phase 1 deviation note said "Phase 2") | Uses the existing privileged provisioning path behind rate limiting | accepted |

---

## 7. Known limitations

1. **Email flows (verification, password reset, invitations) need an email adapter** — not built;
   FR-001 recovery is deferred to the notifications phase (ADR-012).
2. **Playwright/browser-level tests** are not part of this phase's gate evidence.
3. **Rate limiting is per-process** until shared Redis (Phase 5).
4. **Login-CSRF** (forging a victim's login) is mitigated by SameSite=Lax but not yet by a
   pre-session CSRF token; Phase 15 hardening item.
5. The dev header resolver still works in local/test behind the explicit flag — production refuses
   it at startup (unchanged guardrail).

---

## 8. Evidence required from the owner (E-series)

| # | Evidence | Command | Result to record |
|---|---|---|---|
| E1 | Backend gate | `cd backend; uv run pytest` | `168 passed, 10 deselected` |
| E2 | Live integration | `uv run pytest -m integration` | `10 passed` (not skipped) |
| E3 | Frontend gate | `cd frontend; npm ci; npm run lint; npm run typecheck; npm test; npm run build` | all clean, `22 passed` |
| E4 | The real walkthrough | API in one terminal, `npm run dev` in another; register at localhost:5173, see the shell with REAL org/workspace/member data, switch nothing (one org yet), sign out, sign back in | shell renders; no mock data; 401 redirect after logout |

---

## 9. Gate decision

| Condition | State |
|---|---|
| Build list complete (backend auth slice + all §20 frontend items) | Yes |
| Quality gate green (unit + integration + lint + types + build) | Yes [V-today, V-live] |
| Exit-gate walkthrough on the owner's machine | Pending E4 [U] |
| Deviations recorded as ADRs | Yes (0025, 0026, 0024 status) |

**Recommendation:** run E1–E4 on the owner machine. With E4 observed, declare the Phase 2 gate met
and start Phase 3 (category/product catalogue and source contracts) from blueprint section 20.

---

## 10. Revision history

### v1 (initial Phase 2 delivery, 2026-11-21)

Built in the authoring environment and verified against the owner's live Neon; owner-machine
walkthrough pending as E4.
