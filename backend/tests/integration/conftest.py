"""Shared fixtures for integration tests.

The schema is migrated once per integration session (idempotent: ``alembic upgrade
head`` is a no-op when already at head). Every test that needs the database depends
on ``migrated_schema``; if no database URL is configured, the fixture skips and the
whole integration suite is deselected, exactly like Phase 0's connectivity tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from marketpulse.config import Settings

ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = ROOT / "alembic.ini"
MIGRATIONS = ROOT / "migrations"


@pytest.fixture(scope="session")
def integration_settings() -> Settings:
    return Settings()


@pytest.fixture(scope="session")
def migrated_schema(integration_settings: Settings) -> str:
    """Apply the migration head against the direct URL; yield the DSN for tests."""
    dsn = integration_settings.database_direct_dsn or integration_settings.database_dsn
    if dsn is None:
        pytest.skip("MP_DATABASE_DIRECT_URL (or MP_DATABASE_URL) is not set")
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", dsn)
    # Idempotent: a no-op when already at head.
    command.upgrade(cfg, "head")
    yield dsn
    # The schema is left in place; the owner resets the database between runs.


@pytest.fixture
def app_role_dsn(integration_settings: Settings) -> str:
    """The pooled application-role DSN; skip if not configured."""
    dsn = integration_settings.database_dsn
    if dsn is None:
        pytest.skip("MP_DATABASE_URL (application role, pooled) is not set")
    return dsn
