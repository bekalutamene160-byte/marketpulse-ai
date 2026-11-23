# Data model (Phase 2)

The authoritative schema is the Alembic migration `backend/migrations/versions/0001_initial_schema.py`.
This document is a readable summary. The blueprint entity catalogue (section 7.4) is much larger;
Phase 1 implements only the tenant-foundation subset: organizations, users, memberships,
workspaces, and audit events. Everything else arrives in later phases per blueprint section 20.

## Entity-relationship summary

```
organizations  1---*  workspaces
organizations  1---*  memberships  *---1  users
organizations  1---*  audit_events
users          1---*  auth_sessions      (Phase 2)
organizations  1---*  auth_sessions      (nullable active-org pointer, CASCADE)
```

`organizations` is the tenant root. `workspaces`, `memberships`, and `audit_events` carry
`organization_id` and are row-level secured on it. `users` is global (a user may belong to many
organizations); access to it is mediated through the RLS-secured `memberships` join, so a tenant
never sees another tenant's members.

## Tables

### organizations
The tenant root. RLS-enabled: a session sees only the row whose `id` equals
`current_setting('app.tenant_id')`.

| column | type | notes |
|---|---|---|
| id | UUID | primary key |
| slug | VARCHAR(63) | unique; the human identifier |
| display_name | VARCHAR(200) | |
| default_market | VARCHAR(63) | nullable until the owner sets it |
| timezone | VARCHAR(64) | default `UTC` |
| base_currency | VARCHAR(3) | ISO-4217; default `USD` |
| is_demo | BOOLEAN | default false (ADR-0014: demo is a separate tenant) |
| created_at, updated_at | TIMESTAMPTZ | default `now()` |

### users
Global identity. NOT row-level secured (no single tenant to filter by). Phase 1 never exposes it
through the API; Phase 2 adds the auth flow that reads it by email.

| column | type | notes |
|---|---|---|
| id | UUID | primary key |
| email | VARCHAR(320) | unique; stored lowercased |
| password_hash | VARCHAR(255) | Argon2id string; never returned on the domain `User` |
| status | VARCHAR(16) | `active` / `disabled` |
| created_at, updated_at | TIMESTAMPTZ | default `now()` |

### memberships
The user-to-organization link. RLS-enabled on `organization_id`. Unique `(organization_id, user_id)`.

| column | type | notes |
|---|---|---|
| id | UUID | primary key |
| organization_id | UUID | FK organizations(id) ON DELETE CASCADE |
| user_id | UUID | FK users(id) ON DELETE CASCADE |
| role | VARCHAR(16) | owner / admin / member / viewer |
| status | VARCHAR(16) | active / invited / suspended |
| created_at | TIMESTAMPTZ | default `now()` |

### workspaces
A workspace within an organization. RLS-enabled on `organization_id` (USING + WITH CHECK).

| column | type | notes |
|---|---|---|
| id | UUID | primary key |
| organization_id | UUID | FK organizations(id) ON DELETE CASCADE |
| name | VARCHAR(100) | |
| is_read_only | BOOLEAN | default false |
| created_at, updated_at | TIMESTAMPTZ | default `now()` |

### audit_events
Append-only, tenant-scoped audit trail. RLS-enabled on `organization_id`. No UPDATE/DELETE path
through the application; retention is a future admin operation.

| column | type | notes |
|---|---|---|
| id | UUID | primary key |
| organization_id | UUID | FK organizations(id) ON DELETE CASCADE |
| actor_user_id | UUID | nullable (system actions) |
| action | VARCHAR(64) | closed enum, e.g. `organization.created` |
| entity_type | VARCHAR(32) | |
| entity_id | UUID | |
| occurred_at | TIMESTAMPTZ | default `now()` |
| request_id | VARCHAR(64) | ties to the structured log line / trace |
| metadata | JSONB | safe values only (slugs, roles, counts); default `'{}'::jsonb` |

## Indexes
- `ix_workspaces_org_created_at` on `workspaces(organization_id, created_at DESC)` — list workspaces.
- `ix_memberships_organization_id` on `memberships(organization_id)` — list members.
- `ix_audit_events_org_occurred_at` on `audit_events(organization_id, occurred_at DESC)` — audit list.
- `ix_audit_events_org_entity` on `audit_events(organization_id, entity_type, entity_id)` — entity history.

## Row-level security
`ENABLE ROW LEVEL SECURITY` on `organizations`, `memberships`, `workspaces`, `audit_events`. Each
has a `<table>_tenant_isolation` policy:
```sql
FOR ALL
  USING (organization_id::text = current_setting('app.tenant_id', true))   -- id for organizations
  WITH CHECK (organization_id::text = current_setting('app.tenant_id', true))
```
`users` has no RLS. The application role `marketpulse_app` has `NOBYPASSRLS`; see ADR-0022/0023.

### auth_sessions (Phase 2, migration 0002)
Server-side login sessions (ADR-0025). User-scoped like `users`: NO row-level security, no
tenant predicate. The cookie token and CSRF token are stored ONLY as SHA-256 digests.

| column | type | notes |
|---|---|---|
| id | UUID | primary key |
| user_id | UUID | FK users(id) ON DELETE CASCADE; indexed |
| token_hash | VARCHAR(64) | SHA-256 hex of the opaque session token; UNIQUE |
| csrf_token_hash | VARCHAR(64) | SHA-256 hex of the CSRF token bound to the session |
| organization_id | UUID | nullable FK organizations(id) ON DELETE CASCADE — the active org |
| created_at, last_seen_at, expires_at | TIMESTAMPTZ | absolute expiry (default 7 days) |

Phase 2 also adds two SELECT-only per-user RLS policies (ADR-0026):
`memberships_user_access` (a session may read ITS OWN membership rows via `app.user_id`) and
`organizations_user_access` (a member may see the organizations they belong to — the workspace
selector). Writes stay tenant-scoped by the Phase 1 policies.

## Money, time, IDs (blueprint 7.7)
- IDs are UUID v4 (non-enumerable). `created_at`/`occurred_at` carry time ordering.
- Timestamps are `TIMESTAMPTZ` (UTC). Money is deferred to Phase 3/8 (NUMERIC + ISO-4217 currency
  column); Phase 1 only stores the org's `base_currency` code.
