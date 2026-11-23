"""Schema tests that introspect the SQLAlchemy ORM metadata without a database.

These prove the model layer is well-formed and matches the migration's intent: the
five Phase 1 tables exist, tenant-scoped tables carry ``organization_id``, ``users``
is global, the unique and JSONB constraints are present, and every table compiles to
valid PostgreSQL CREATE TABLE DDL. The live migration is verified separately in
test_migrations.py and the integration tests.
"""

from __future__ import annotations

from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

import marketpulse.infrastructure.db.models  # noqa: F401  - registers models on Base.metadata
from marketpulse.infrastructure.db.base import Base

EXPECTED = {"organizations", "users", "memberships", "workspaces", "audit_events"}
TENANT_SCOPED = {"memberships", "workspaces", "audit_events"}


def test_all_phase1_tables_registered_on_metadata() -> None:
    assert set(Base.metadata.tables) >= EXPECTED


def test_tenant_scoped_tables_carry_organization_id() -> None:
    for table in TENANT_SCOPED:
        assert "organization_id" in Base.metadata.tables[table].c


def test_users_is_global_and_has_no_organization_id() -> None:
    assert "organization_id" not in Base.metadata.tables["users"].c


def test_unique_constraints_are_present() -> None:
    assert Base.metadata.tables["organizations"].c.slug.unique
    assert Base.metadata.tables["users"].c.email.unique


def test_membership_has_unique_org_user_constraint() -> None:
    table = Base.metadata.tables["memberships"]
    uqs = [c for c in table.constraints if isinstance(c, UniqueConstraint)]
    assert any(sorted(c.columns.keys()) == ["organization_id", "user_id"] for c in uqs)


def test_audit_events_metadata_column_is_jsonb() -> None:
    col = Base.metadata.tables["audit_events"].c["metadata"]
    assert isinstance(col.type, postgresql.JSONB)


def test_every_table_has_a_single_uuid_primary_key() -> None:
    for table in EXPECTED:
        pks = [c for c in Base.metadata.tables[table].c if c.primary_key]
        assert len(pks) == 1
        assert isinstance(pks[0].type, postgresql.UUID)


def test_every_table_compiles_to_create_table_ddr() -> None:
    for table in EXPECTED:
        ddl = str(CreateTable(Base.metadata.tables[table]).compile(dialect=postgresql.dialect()))
        assert f"CREATE TABLE {table}" in ddl


# --- Phase 2: auth_sessions model ---
def test_auth_sessions_table_registered_and_shaped() -> None:
    table = Base.metadata.tables["auth_sessions"]
    assert "user_id" in table.c
    assert "token_hash" in table.c
    assert "csrf_token_hash" in table.c
    assert "expires_at" in table.c
    # Only digests are stored: no raw-token column may ever exist.
    assert "token" not in table.c
    assert "csrf_token" not in table.c


def test_auth_sessions_has_no_organization_id_tenant_column_requirement() -> None:
    # Sessions are user-scoped (like users); the optional organization_id is the
    # ACTIVE org pointer, not a tenant predicate, and the table has no RLS.
    assert "organization_id" in Base.metadata.tables["auth_sessions"].c
