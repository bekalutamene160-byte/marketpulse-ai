"""Auth sessions: server-side login sessions and the per-user membership policy.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-21

Phase 2 replaces the dev tenant header (ADR-0024) with real authentication. This
migration adds:

1. ``auth_sessions`` — the server-side session store. The cookie carries an opaque
   random token; only its SHA-256 hash is stored, so a database leak cannot be
   replayed as a login. Sessions belong to a USER (like ``users``, global identity),
   not to a tenant, so the table has no row-level security and no ``organization_id``
   tenant predicate — the optional ``organization_id`` column is the user's ACTIVE
   organization (the workspace selector), with ON DELETE CASCADE so deleting an org
   never leaves a session pointing at it.

2. A second, narrower SELECT policy on ``memberships``:
       USING (user_id::text = current_setting('app.user_id', true))
   The tenant policy (0001) lets a session see memberships of its CURRENT tenant only.
   The workspace selector must list ALL of the signed-in user's memberships across
   organizations. This policy allows a session to see exactly its OWN membership rows
   (user GUC matches the row) and nothing else. With no ``app.user_id`` set the
   expression is NULL and matches nothing — default-deny is preserved and is proven by
   a live integration test.

3. Least-privilege grants for the app role on ``auth_sessions``: the full session
   lifecycle (create/read/touch/delete) is an application concern. Deliberately NOT
   granted: UPDATE on ``users`` (transparent password re-hash is deferred; the app
   role keeps read-only access to the global identity table — ADR-0025).
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# A role name is interpolated into GRANT DDL, so it MUST be a safe unquoted Postgres
# identifier — the same rule migration 0001 and Settings.db_app_role enforce.
_ROLE_NAME = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


def _app_role() -> str:
    """Read and validate the application role name from the environment."""
    role = os.environ.get("MP_DB_APP_ROLE", "marketpulse_app")
    if not _ROLE_NAME.match(role):
        raise RuntimeError(
            f"MP_DB_APP_ROLE {role!r} is not a safe role name "
            "(must start with a lowercase letter and contain only a-z0-9_)."
        )
    return role


def _user_predicate() -> str:
    """The USING expression comparing user_id to the per-user GUC (NULL when unset)."""
    return "user_id::text = current_setting('app.user_id', true)"


def upgrade() -> None:
    op.create_table(
        "auth_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # SHA-256 hex of the opaque session token. Unique: one row per token.
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        # SHA-256 hex of the CSRF token bound to this session (double-submit check).
        sa.Column("csrf_token_hash", sa.String(64), nullable=False),
        # The user's ACTIVE organization (workspace selector). Nullable: cleared on
        # org deletion via CASCADE, and a user with no membership has none.
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "last_seen_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])

    # Per-user membership visibility (ADR-0026). SELECT only: the user can read their
    # own membership rows across tenants; writes stay tenant-scoped by the 0001 policy.
    op.execute(
        "CREATE POLICY memberships_user_access ON memberships "
        f"FOR SELECT USING ({_user_predicate()})"
    )

    # Per-user organization visibility: a member may SEE the organizations they
    # belong to (the workspace selector needs their names), but nothing more —
    # writes and non-member orgs stay hidden. The subquery is itself RLS-filtered
    # (the memberships policies above), so a session sees exactly the orgs it has a
    # membership row for. With no app.user_id GUC the subquery is empty: default-deny.
    op.execute(
        "CREATE POLICY organizations_user_access ON organizations "
        "FOR SELECT USING ("
        "id IN (SELECT organization_id FROM memberships "
        f"WHERE {_user_predicate()}))"
    )

    # Session lifecycle is the application role's job (login/logout/me/switch/GC).
    app_role = _app_role()
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON auth_sessions TO {app_role}")
    # The tenant policy grants SELECT on memberships already (0001); the new policy
    # needs no extra grant. No UPDATE ON users by design (see ADR-0025).


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS organizations_user_access ON organizations")
    op.execute("DROP POLICY IF EXISTS memberships_user_access ON memberships")
    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
