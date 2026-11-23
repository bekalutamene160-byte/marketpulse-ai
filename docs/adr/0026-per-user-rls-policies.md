# ADR 0026: Per-user row-level security policies for memberships and organizations

- Status: accepted
- Date: 2026-11-21
- Blueprint reference: 7.6 (tenant isolation), 15.4 (tenant isolation), 14.1 (auth/me, members)
- Extends ADR-0022 (tenant context via SET LOCAL + RLS) — it does not replace it

## Context

The Phase 1 tenant policy allows a session to see exactly ONE organization's rows:
the one in `app.tenant_id`. Authentication created two legitimate cross-tenant
reads that the tenant policy alone cannot serve:

1. **The workspace selector** (`GET /auth/me`) must list ALL of the signed-in
   user's memberships across organizations, with each organization's name.
2. **The member list** (`GET /organizations/members`) needs the emails behind the
   current tenant's membership rows.

Both must run under the least-privilege application role. Granting bypass, wider
grants, or moving the check to application code only would each weaken the
database-level guarantee.

## Decision

Migration 0002 adds two SELECT-only policies, both keyed on a transaction-local
`app.user_id` GUC (set the same way as `app.tenant_id`: parameterized
`set_config(..., true)`, reset at COMMIT):

```sql
CREATE POLICY memberships_user_access ON memberships
  FOR SELECT USING (user_id::text = current_setting('app.user_id', true));

CREATE POLICY organizations_user_access ON organizations
  FOR SELECT USING (
    id IN (SELECT organization_id FROM memberships
           WHERE user_id::text = current_setting('app.user_id', true)));
```

- Multiple permissive policies OR together: a session sees rows satisfying the
  tenant policy OR the user policy. Writes are unchanged — only the 0001 tenant
  policies have `WITH CHECK`.
- The organizations subquery is itself RLS-filtered by the memberships policies,
  so a session sees exactly the organizations it has a membership row for. A
  member can SEE an org they belong to (name/settings for the selector) but still
  only WRITE inside the tenant context.
- With NO `app.user_id` set, both policies compare against NULL and match nothing:
  default-deny is preserved (proven by a live test that reads zero rows with no
  GUC).

## Alternatives considered

- **Denormalize org names into memberships:** rejected — a second copy of the
  name drifts and still leaks nothing less.
- **Run the selector query on the owner connection:** rejected — the API must not
  use the privileged role for request work (ADR-0023).
- **Application-level filtering only:** rejected — a repository bug would become a
  cross-tenant leak instead of an empty result.

## Consequences

- `set_tenant_context` already sets `app.user_id` whenever the context carries a
  user, so tenant-scoped requests transparently gain their own memberships.
- On a PLAIN (tenant-less) session — login, logout, switch — the
  `SqlAlchemyMembershipByUserReader` adapter sets `app.user_id` itself before
  reading; the switch flow then sets `app.tenant_id` via the scope adapter to read
  exactly one organization row after the membership check.
- Cross-tenant enumeration remains impossible: a user sees their own membership
  rows and the names of their own organizations. Other tenants' data (audit
  events, workspaces) stays invisible — proven by the Phase 1 isolation suite,
  which still passes unchanged.

## Verification

`tests/integration/test_auth_live.py` (live Neon): membership list grows with a
second org; both organization rows readable via `list_by_ids`; zero rows with no
GUC; the Phase 1 `test_tenant_isolation.py` suite passes unchanged.
