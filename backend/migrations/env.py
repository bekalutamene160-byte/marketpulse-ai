"""Alembic migration environment (ADR-0022, ADR-0023).

Migrations run against the DIRECT (non-pooled) connection, as the project OWNER
role. PgBouncer transaction mode on Neon's pooled URL breaks DDL and session-level
``SET``, so migrations must never go through it. The URL is resolved from
``MP_DATABASE_DIRECT_URL``, falling back to ``MP_DATABASE_URL`` for local parity
against a non-pooled local database.

The application role (``marketpulse_app``) is NOT used for migrations: it owns no
tables and cannot create them. The role itself is created once by
``scripts/db/bootstrap_app_role.py``; this migration assumes it exists and GRANTs
it the privileges it needs (ADR-0023). Run bootstrap before the first migration.

Row-level security policies and the app-role GRANTs are part of the migration so
that a freshly migrated database is tenant-safe by construction, not by a separate
manual step that can be forgotten (blueprint Phase 1 exit gate).
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import marketpulse.infrastructure.db.models  # noqa: F401  - registers models on Base.metadata
from marketpulse.config import Settings
from marketpulse.infrastructure.db.base import Base

# this is the Alembic Config object from alembic.ini.
config = context.config

# Interpret the config file for Python logging if present.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _migration_url() -> str | None:
    """Resolve the DDL connection URL: direct URL preferred, pooled URL as fallback."""
    # Settings() reads the real environment and .env. Validation failures here mean
    # the deployment is misconfigured; surfacing them during migration is correct.
    try:
        settings = Settings()
    except Exception:  # noqa: BLE001 - any config failure means "no usable URL"
        return None
    return settings.database_direct_dsn or settings.database_dsn


_url = _migration_url()
if _url is not None:
    config.set_main_option("sqlalchemy.url", _url)

# The single source of truth for the schema. Autogenerate compares against this.
target_metadata = Base.metadata

# A dummy postgresql URL used ONLY for offline SQL generation when no real URL is
# configured. Offline mode never connects; it only needs the dialect to render DDL.
# This lets `alembic upgrade head --sql` work in any environment for verification.
_OFFLINE_FALLBACK_URL = "postgresql://marketpulse:marketpulse@localhost/marketpulse"


def run_migrations_offline() -> None:
    """Generate SQL without a live connection (``alembic upgrade --sql``)."""
    url = config.get_main_option("sqlalchemy.url") or _OFFLINE_FALLBACK_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection."""
    if not config.get_main_option("sqlalchemy.url"):
        raise RuntimeError(
            "No database URL configured for migrations. Set MP_DATABASE_DIRECT_URL "
            "(preferred, owner role) or MP_DATABASE_URL. See docs/DEPLOYMENT.md."
        )
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
