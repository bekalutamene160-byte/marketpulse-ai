"""Migration tests: render the initial migration to SQL offline (no database needed)
and assert it builds the schema, RLS policies, and least-privilege grants that the
Phase 1 exit gate requires. A live upgrade/downgrade is verified by the integration
tests against a real PostgreSQL.
"""

from __future__ import annotations

import ast
import contextlib
import io
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = ROOT / "alembic.ini"
MIGRATIONS = ROOT / "migrations"
INITIAL = MIGRATIONS / "versions" / "0001_initial_schema.py"


@pytest.fixture
def offline_sql(monkeypatch: pytest.MonkeyPatch) -> str:
    # Deterministic: no real URL, the default app role. env.py falls back to a dummy
    # postgresql URL for offline DDL rendering (it never connects).
    monkeypatch.setenv("MP_DATABASE_URL", "")
    monkeypatch.setenv("MP_DATABASE_DIRECT_URL", "")
    monkeypatch.setenv("MP_DB_APP_ROLE", "marketpulse_app")
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(MIGRATIONS))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        command.upgrade(cfg, "head", sql=True)
    return buf.getvalue()


def test_offline_sql_creates_every_phase1_table(offline_sql: str) -> None:
    for table in ("organizations", "users", "memberships", "workspaces", "audit_events"):
        assert f"CREATE TABLE {table}" in offline_sql, table


def test_offline_sql_enables_rls_on_tenant_scoped_tables(offline_sql: str) -> None:
    for table in ("organizations", "memberships", "workspaces", "audit_events"):
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in offline_sql, table


def test_offline_sql_does_not_enable_rls_on_users(offline_sql: str) -> None:
    # users is global identity; access is mediated through the RLS-secured memberships.
    assert "ALTER TABLE users ENABLE ROW LEVEL SECURITY" not in offline_sql


def test_offline_sql_creates_tenant_isolation_policies_with_check(offline_sql: str) -> None:
    assert "CREATE POLICY organizations_tenant_isolation" in offline_sql
    assert "CREATE POLICY workspaces_tenant_isolation" in offline_sql
    assert "CREATE POLICY audit_events_tenant_isolation" in offline_sql
    # The default-deny GUC read: current_setting(..., true) returns NULL when unset.
    assert "current_setting('app.tenant_id', true)" in offline_sql
    # WITH CHECK prevents inserting a row for a different tenant.
    assert "WITH CHECK" in offline_sql


def test_offline_sql_grants_least_privilege_to_the_app_role(offline_sql: str) -> None:
    assert "GRANT USAGE ON SCHEMA public TO marketpulse_app" in offline_sql
    assert "GRANT SELECT ON organizations, memberships, users TO marketpulse_app" in offline_sql
    assert "GRANT SELECT, INSERT, UPDATE ON workspaces TO marketpulse_app" in offline_sql
    assert "GRANT SELECT, INSERT ON audit_events TO marketpulse_app" in offline_sql


def test_offline_sql_creates_indexes_for_read_paths(offline_sql: str) -> None:
    assert "ix_workspaces_org_created_at" in offline_sql
    assert "ix_audit_events_org_occurred_at" in offline_sql
    assert "ix_audit_events_org_entity" in offline_sql


def test_initial_migration_module_has_upgrade_and_downgrade() -> None:
    tree = ast.parse(INITIAL.read_text(encoding="utf-8"))
    names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert {"upgrade", "downgrade"} <= names


# --- Phase 2: migration 0002 (auth sessions + per-user policies) ---

AUTH_SESSIONS = MIGRATIONS / "versions" / "0002_auth_sessions.py"


def test_offline_sql_creates_the_auth_sessions_table(offline_sql: str) -> None:
    assert "CREATE TABLE auth_sessions" in offline_sql
    # The raw token NEVER lands in the schema: only a 64-char digest column exists.
    assert "token_hash" in offline_sql
    assert "expires_at" in offline_sql


def test_offline_sql_adds_the_per_user_membership_policy(offline_sql: str) -> None:
    assert "CREATE POLICY memberships_user_access" in offline_sql
    assert "user_id::text = current_setting('app.user_id', true)" in offline_sql


def test_offline_sql_adds_the_per_user_organization_policy(offline_sql: str) -> None:
    # A member may SEE the organizations they belong to (workspace selector names),
    # but nothing more: the subquery is itself RLS-filtered by the memberships policy.
    assert "CREATE POLICY organizations_user_access" in offline_sql
    assert "id IN (SELECT organization_id FROM memberships" in offline_sql


def test_offline_sql_grants_the_session_lifecycle_to_the_app_role(offline_sql: str) -> None:
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON auth_sessions TO marketpulse_app" in offline_sql
    # Deliberately absent: UPDATE on users (transparent re-hash is deferred, ADR-0025).
    assert "GRANT UPDATE ON users" not in offline_sql


def test_second_migration_module_has_upgrade_and_downgrade() -> None:
    tree = ast.parse(AUTH_SESSIONS.read_text(encoding="utf-8"))
    names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert {"upgrade", "downgrade"} <= names
