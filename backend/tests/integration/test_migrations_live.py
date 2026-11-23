"""Integration test: the migration applied cleanly and the schema + RLS are in place.

Phase 1 exit gate: "migration from empty DB succeeds". Depends on the session-scoped
``migrated_schema`` fixture (which applied ``alembic upgrade head``).

    MP_DATABASE_DIRECT_URL=postgresql://owner:pw@host/db \
    uv run pytest -m integration tests/integration/test_migrations_live.py
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.integration

TENANT_TABLES = ("organizations", "memberships", "workspaces", "audit_events")
ALL_TABLES = TENANT_TABLES + ("users",)


def test_all_phase1_tables_exist(migrated_schema: str) -> None:
    engine = create_engine(migrated_schema)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                )
            )
            tables = {r[0] for r in rows}
            assert set(ALL_TABLES) <= tables
    finally:
        engine.dispose()


def test_rls_is_enabled_on_tenant_scoped_tables(migrated_schema: str) -> None:
    engine = create_engine(migrated_schema)
    try:
        with engine.connect() as conn:
            for table in TENANT_TABLES:
                enabled = conn.execute(
                    text("SELECT relrowsecurity FROM pg_class WHERE relname = :t"),
                    {"t": table},
                ).scalar()
                assert enabled is True, f"RLS not enabled on {table}"
    finally:
        engine.dispose()


def test_tenant_isolation_policies_exist(migrated_schema: str) -> None:
    engine = create_engine(migrated_schema)
    try:
        with engine.connect() as conn:
            for table in TENANT_TABLES:
                count = conn.execute(
                    text(
                        "SELECT count(*) FROM pg_policies "
                        "WHERE tablename = :t AND policyname LIKE '%_tenant_isolation'"
                    ),
                    {"t": table},
                ).scalar()
                assert count == 1, f"no tenant_isolation policy on {table}"
    finally:
        engine.dispose()
