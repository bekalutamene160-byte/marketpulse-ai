"""Initial schema: tenant foundation, row-level security, app-role grants.

Revision ID: 0001
Revises:
Create Date: 2026-11-20

This migration is the single source of truth for the Phase 1 schema. It creates the
five tenant-foundation tables, the indexes the read paths need, the row-level
security policies that enforce tenant isolation at the database (ADR-0022), and the
least-privilege GRANTs to the application role (ADR-0023).

Order matters and is deliberate:
  1. Create tables and indexes (owner role, direct connection).
  2. ENABLE ROW LEVEL SECURITY on every tenant-scoped table. The table owner still
     bypasses RLS (no FORCE), so provisioning/migrations via the owner keep working;
     the application role (non-owner, NOBYPASSRLS) is subject to RLS.
  3. CREATE POLICY with USING + WITH CHECK comparing organization_id (or id for the
     organizations root) to current_setting('app.tenant_id', true). The 'true' arg
     makes an unset GUC return NULL rather than raise, so the system is default-deny
     until a tenant is explicitly established.
  4. GRANT only the privileges the application role needs. With RLS enabled and no
     GRANT, the role would see nothing; the GRANT plus the policy together give
     least-privilege tenant-scoped access.

The application role itself is created once by scripts/db/bootstrap_app_role.py
(this migration assumes it exists). Run bootstrap before the first ``alembic upgrade``.
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Tables that carry organization_id and so are row-level secured. `users` is
# intentionally absent: it is global identity, and access is mediated through the
# RLS-secured `memberships` join.
_TENANT_TABLES_ORG_SCOPED = ("memberships", "workspaces", "audit_events")

# A role name is interpolated into GRANT DDL, so it MUST be a safe unquoted
# Postgres identifier: start with a lowercase letter, then letters/digits/underscore.
# The same rule used in Settings.db_app_role is enforced before any interpolation,
# so a misconfigured env var can never become a SQL injection vector.
_ROLE_NAME = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


def _tenant_predicate(column: str) -> str:
    """The USING/WITH CHECK expression comparing a column to the tenant GUC."""
    return f"{column}::text = current_setting('app.tenant_id', true)"


def _app_role() -> str:
    """Read and validate the application role name from the environment."""
    role = os.environ.get("MP_DB_APP_ROLE", "marketpulse_app")
    if not _ROLE_NAME.match(role):
        raise RuntimeError(
            f"MP_DB_APP_ROLE {role!r} is not a safe role name "
            "(must start with a lowercase letter and contain only a-z0-9_)."
        )
    return role


def upgrade() -> None:
    app_role = _app_role()
    # --- tables ---
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(63), nullable=False, unique=True),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("default_market", sa.String(63), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("base_currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    op.create_table(
        "memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_memberships_org_user"),
    )

    op.create_table(
        "workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_read_only", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "occurred_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("request_id", sa.String(64), nullable=False, server_default="-"),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
    )

    # --- indexes (the read paths the application uses) ---
    op.create_index(
        "ix_workspaces_org_created_at",
        "workspaces",
        ["organization_id", sa.text("created_at DESC")],
    )
    op.create_index("ix_memberships_organization_id", "memberships", ["organization_id"])
    op.create_index(
        "ix_audit_events_org_occurred_at",
        "audit_events",
        ["organization_id", sa.text("occurred_at DESC")],
    )
    op.create_index(
        "ix_audit_events_org_entity",
        "audit_events",
        ["organization_id", "entity_type", "entity_id"],
    )

    # --- row-level security (ADR-0022) ---
    # The organizations root: a session sees only the row whose id equals the tenant GUC.
    op.execute("ALTER TABLE organizations ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY organizations_tenant_isolation ON organizations "
        f"FOR ALL USING ({_tenant_predicate('id')}) "
        f"WITH CHECK ({_tenant_predicate('id')})"
    )
    # Every organization_id-carrying table: same pattern against organization_id.
    for table in _TENANT_TABLES_ORG_SCOPED:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"FOR ALL USING ({_tenant_predicate('organization_id')}) "
            f"WITH CHECK ({_tenant_predicate('organization_id')})"
        )

    # --- least-privilege grants to the application role (ADR-0023) ---
    # The role must be able to reach the schema and the rows RLS lets it see.
    op.execute(f"GRANT USAGE ON SCHEMA public TO {app_role}")
    # organizations: read the current tenant only (creates are provisioning/owner).
    op.execute(f"GRANT SELECT ON organizations, memberships, users TO {app_role}")
    # workspaces: list and create within the current tenant.
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON workspaces TO {app_role}")
    # audit_events: append-only through the app (insert + read), never update/delete.
    op.execute(f"GRANT SELECT, INSERT ON audit_events TO {app_role}")


def downgrade() -> None:
    # Policies are dropped with their tables; reverse FK order for the drop.
    op.drop_table("audit_events")
    op.drop_table("workspaces")
    op.drop_table("memberships")
    op.drop_table("users")
    op.drop_table("organizations")
