"""Typed, validated runtime configuration.

Values come from environment variables prefixed with ``MP_`` and, for local work, from a
``.env`` file in the current directory. Real environment variables always win over ``.env``.

Design rules (blueprint 19.4):
- Validate at startup. A bad value must crash the process immediately.
- Fail closed. staging/production refuse to start with a missing or insecure setting
  instead of silently falling back to a development default.
- Secrets are ``SecretStr`` so they never appear in logs, reprs, or error messages.
- No business data here. Markets, currencies and categories are tenant data that live in
  the database (blueprint 4.1, principle 11), never in process configuration.

Phase 1 adds the migration/app-role settings (ADR-0022, ADR-0023) and the dev tenant
header switch (ADR-0024).
"""

import re
from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "test", "staging", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

_POSTGRES_PREFIXES = ("postgresql://", "postgres://", "postgresql+psycopg://")
_REDIS_PREFIXES = ("redis://", "rediss://")
_TLS_SSLMODES = ("sslmode=require", "sslmode=verify-ca", "sslmode=verify-full")

# A role name is interpolated into DDL/GRANTs, so it must be a safe unquoted
# Postgres identifier: start with a lowercase letter, then letters/digits/underscore.
# Underscores are allowed (they are valid in Postgres identifiers, e.g.
# `marketpulse_app`); hyphens are not, because they would require quoting.
_ROLE_NAME = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="MP_",
        case_sensitive=False,
        extra="ignore",  # unrelated environment variables are not an error
        # A failed validation must never echo the offending value: it may be a password.
        hide_input_in_errors=True,
    )

    environment: Environment = "local"
    log_level: LogLevel = "INFO"
    log_json: bool = False  # JSON lines for log aggregators; plain text for humans

    # PostgreSQL system of record (blueprint ADR-002). Optional only so that local
    # development can start before a database exists; readiness reports it honestly.
    # This is the POOLED connection the application uses, connected as marketpulse_app.
    database_url: SecretStr | None = None
    # The DIRECT (non-pooled) connection, connected as the project owner. Used only by
    # Alembic migrations and the app-role bootstrap (ADR-0023). PgBouncer transaction
    # mode on the pooled URL breaks DDL and session-level SET, so migrations must avoid
    # it. The bootstrap script and migrations/env.py read this; the running app does not.
    database_direct_url: SecretStr | None = None
    # Redis is only the job transport, never the system of record (ADR-003).
    redis_url: SecretStr | None = None

    # The least-privilege application role created by scripts/db/bootstrap_app_role.py.
    # It owns no tables and has NOBYPASSRLS; RLS is the defense in depth (ADR-0022).
    db_app_role: str = "marketpulse_app"
    db_app_password: SecretStr | None = None

    # Neon scales to zero after idle time, so the first connection can be slow.
    probe_timeout_seconds: float = Field(default=10.0, gt=0, le=60)

    # DB connection pool sizing. Neon's pooled endpoint already runs PgBouncer in
    # transaction mode, so the application's own pool stays small. pre_ping defends
    # against stale connections after Neon scale-to-zero.
    db_pool_size: int = Field(default=5, ge=1, le=20)
    db_max_overflow: int = Field(default=5, ge=0, le=20)

    # Phase 1 dev/test ONLY (ADR-0024): a header resolver trusts X-MP-Organization /
    # X-MP-User to set tenant context until Phase 2 ships auth-backed resolution.
    # Fail-closed: enabling this anywhere outside local/test refuses to start.
    enable_dev_tenant_header: bool = False

    # Phase 2 authentication (ADR-0025). Sessions have an absolute lifetime (no
    # sliding renewal); login/register are rate limited per client IP with a fixed
    # window. The limiter is in-process: exact for the single-process Phase 2 shape,
    # per-replica behind multiple instances until Phase 5 moves counters to Redis.
    session_lifetime_hours: int = Field(default=168, ge=1, le=720)
    auth_rate_limit_attempts: int = Field(default=10, ge=1, le=100)
    auth_rate_limit_window_seconds: int = Field(default=300, ge=10, le=3600)

    # As an environment variable this must be JSON: MP_CORS_ORIGINS='["http://localhost:5173"]'
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalise_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @field_validator("db_app_role", mode="after")
    @classmethod
    def _check_app_role_name(cls, value: str) -> str:
        # A role name is interpolated into DDL/GRANTs; it must be a safe identifier.
        if not _ROLE_NAME.match(value):
            raise ValueError(
                "db_app_role must be a lowercase identifier (a-z0-9_, start with a letter)"
            )
        return value

    @field_validator("database_url", "database_direct_url", "redis_url", mode="before")
    @classmethod
    def _blank_means_unset(cls, value: object) -> object:
        # `MP_DATABASE_URL=` in a .env file should mean "not configured", not "invalid".
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("database_url", "database_direct_url")
    @classmethod
    def _check_database_scheme(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not value.get_secret_value().startswith(_POSTGRES_PREFIXES):
            raise ValueError("database_url must be a PostgreSQL URL (postgresql://...)")
        return value

    @field_validator("redis_url")
    @classmethod
    def _check_redis_scheme(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not value.get_secret_value().startswith(_REDIS_PREFIXES):
            raise ValueError("redis_url must be a Redis URL (redis:// or rediss://)")
        return value

    @model_validator(mode="after")
    def _non_local_guardrails(self) -> Self:
        if self.environment in ("staging", "production"):
            if self.database_url is None:
                raise ValueError(f"database_url is required in {self.environment}")
            if not any(mode in self.database_url.get_secret_value() for mode in _TLS_SSLMODES):
                raise ValueError("database_url must enforce TLS (sslmode=require or stricter)")
            if "*" in self.cors_origins:
                raise ValueError(f"wildcard CORS origins are not allowed in {self.environment}")
            # The dev header resolver trusts the client. It must never run where real
            # tenants exist (ADR-0024). Phase 2 replaces it with auth-backed resolution.
            if self.enable_dev_tenant_header:
                raise ValueError(
                    f"enable_dev_tenant_header is forbidden in {self.environment}; "
                    "tenant context must come from authentication (Phase 2)."
                )
        if self.environment == "production":
            if self.redis_url is None:
                raise ValueError("redis_url is required in production")
            if not self.redis_url.get_secret_value().startswith("rediss://"):
                raise ValueError("redis_url must use TLS (rediss://) in production")
        return self

    @property
    def database_dsn(self) -> str | None:
        """libpq-style URL for psycopg (drops SQLAlchemy's `+psycopg` driver suffix)."""
        return self._strip_driver(self.database_url)

    @property
    def database_direct_dsn(self) -> str | None:
        """Direct (non-pooled) libpq URL for migrations and the role bootstrap."""
        return self._strip_driver(self.database_direct_url)

    @staticmethod
    def _strip_driver(value: SecretStr | None) -> str | None:
        if value is None:
            return None
        return value.get_secret_value().replace("postgresql+psycopg://", "postgresql://", 1)

    @property
    def redis_dsn(self) -> str | None:
        return None if self.redis_url is None else self.redis_url.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    """Build settings once per process. Tests pass explicit Settings instead of using this."""
    return Settings()
