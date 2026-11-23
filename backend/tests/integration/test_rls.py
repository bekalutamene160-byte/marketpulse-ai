"""Integration test: the application role cannot bypass RLS, and a session with no
tenant context sees nothing (default-deny). Phase 1 exit gate: "DB role cannot
bypass RLS".

    MP_DATABASE_URL=postgresql://marketpulse_app:pw@host/db \
    MP_DATABASE_DIRECT_URL=postgresql://owner:pw@host/db \
    uv run pytest -m integration tests/integration/test_rls.py
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text

from marketpulse.core.tenancy import TenantContext
from marketpulse.infrastructure.db.session import DatabaseSessionManager, set_tenant_context

pytestmark = pytest.mark.integration


def test_app_role_has_no_bypassrls(app_role_dsn: str) -> None:
    engine = create_engine(app_role_dsn)
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user")
            ).one()
            assert row[0] is False, "application role has BYPASSRLS=true"
    finally:
        engine.dispose()


def test_default_deny_when_tenant_context_unset(migrated_schema: str, app_role_dsn: str) -> None:
    # Seed one workspace as the owner so the table is non-empty.
    priv = create_engine(migrated_schema)
    try:
        with priv.connect() as conn, conn.begin():
            conn.execute(
                text(
                    "INSERT INTO organizations (id, slug, display_name, timezone, "
                    "base_currency, is_demo) "
                    "VALUES (:id, :slug, :dn, 'UTC', 'USD', false) "
                    "ON CONFLICT (slug) DO NOTHING"
                ),
                {"id": str(uuid.uuid4()), "slug": "rls-seed", "dn": "RLS Seed"},
            )
            conn.execute(
                text(
                    "INSERT INTO workspaces (id, organization_id, name, is_read_only) "
                    "SELECT :wid, id, 'seed', false FROM organizations WHERE slug='rls-seed'"
                ),
                {"wid": str(uuid.uuid4())},
            )
    finally:
        priv.dispose()

    # As the application role with NO tenant context: default-deny must hide the row.
    mgr = DatabaseSessionManager.from_dsn(app_role_dsn, pool_size=1, max_overflow=0)
    try:
        session = mgr.session_factory()
        try:
            with session.begin():
                count = session.execute(text("SELECT count(*) FROM workspaces")).scalar()
                assert count == 0, "rows visible without tenant context (RLS default-deny broken)"
        finally:
            session.close()
    finally:
        mgr.dispose()


def test_tenant_context_grants_visibility(migrated_schema: str, app_role_dsn: str) -> None:
    # The seeded org's slug is 'rls-seed'; look up its id as the owner.
    priv = create_engine(migrated_schema)
    try:
        with priv.connect() as conn:
            org_id = conn.execute(
                text("SELECT id FROM organizations WHERE slug = 'rls-seed'")
            ).scalar()
    finally:
        priv.dispose()
    if org_id is None:
        pytest.skip("rls-seed org not present; run with the default-deny test")

    mgr = DatabaseSessionManager.from_dsn(app_role_dsn, pool_size=1, max_overflow=0)
    try:
        session = mgr.session_factory()
        try:
            with session.begin():
                set_tenant_context(session, TenantContext(organization_id=org_id))
                count = session.execute(text("SELECT count(*) FROM workspaces")).scalar()
                assert count >= 1, "seeded row not visible under the matching tenant context"
        finally:
            session.close()
    finally:
        mgr.dispose()
