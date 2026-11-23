"""PostgreSQL session lifecycle and tenant-context propagation (blueprint Phase 1).

This module owns three things:

1. The SQLAlchemy engine and session factory for the APPLICATION role (pooled
   connection, ADR-0022/0023). The application role is least-privilege and has
   NOBYPASSRLS; row-level security enforces tenant isolation on top of it.

2. ``set_tenant_context``: the only place the tenant identity is pushed onto a
   database session. It uses ``set_config(name, value, is_local=true)`` — a normal
   SQL function that accepts bound parameters, so the tenant id is NEVER
   string-interpolated into SQL (no injection surface). ``is_local=true`` makes the
   setting equivalent to ``SET LOCAL``: scoped to the current transaction and reset
   at COMMIT/ROLLBACK. That is mandatory under PgBouncer transaction-mode pooling
   (Neon pooled endpoint), where a session-level ``SET`` would leak to the next
   tenant that reuses the server-side connection (threat T10).

3. A request-scoped FastAPI dependency that opens a transaction, sets the tenant
   GUCs, yields the session, and commits or rolls back. ``SET LOCAL`` only takes
   effect inside a transaction, so the dependency always begins one explicitly.

The session strategy is synchronous SQLAlchemy 2.x with psycopg3, accessed from
sync FastAPI endpoints (run in Starlette's threadpool). psycopg's async mode
refuses to run on Windows' default ProactorEventLoop (ADR-0021); a threadpool
works on every OS and keeps the transaction boundary explicit and predictable.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from marketpulse.config import Settings
from marketpulse.core.logging import request_id_var
from marketpulse.core.tenancy import TenantContext


def set_tenant_context(session: Session, ctx: TenantContext) -> None:
    """Set the transaction-local tenant GUCs on ``session``'s connection.

    Must be called AFTER the session's transaction has begun (``SET LOCAL`` only
    applies inside a transaction). The dependency in ``api/deps`` guarantees this.
    If a GUC is unset at the database, RLS policies compare against NULL and match
    nothing: the system is default-deny until a tenant is explicitly established.
    """
    # set_config(setting_name, new_value, is_local) -> text. Bound parameter means
    # the UUID string is sent via the extended query protocol, never interpolated.
    session.execute(
        text("SELECT set_config('app.tenant_id', :tid, true)"),
        {"tid": str(ctx.organization_id)},
    )
    if ctx.workspace_id is not None:
        session.execute(
            text("SELECT set_config('app.workspace_id', :wid, true)"),
            {"wid": str(ctx.workspace_id)},
        )
    if ctx.user_id is not None:
        session.execute(
            text("SELECT set_config('app.user_id', :uid, true)"),
            {"uid": str(ctx.user_id)},
        )


@dataclass(frozen=True, slots=True)
class DatabaseSessionManager:
    """Owns the engine and session factory for one connection role.

    Two instances exist in practice: the APPLICATION manager (pooled, app role,
    RLS-enforced) wired into ``create_app``, and a PRIVILEGED manager (direct,
    owner role, RLS-bypassed) used by the provisioning service, bootstrap script
    and migration runner. Keeping them separate prevents the app role from ever
    inheriting owner privileges by accident.
    """

    engine: Engine
    session_factory: sessionmaker[Session]

    def dispose(self) -> None:
        self.engine.dispose()

    @classmethod
    def from_dsn(
        cls, dsn: str, *, pool_size: int = 5, max_overflow: int = 5, pool_recycle: int = 900
    ) -> DatabaseSessionManager:
        engine = create_engine(
            dsn,
            poolclass=QueuePool,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=True,  # Neon scale-to-zero leaves stale connections
            pool_recycle=pool_recycle,
            future=True,
        )
        # expire_on_commit=False: mapped domain entities stay usable after commit.
        # autoflush=False: no surprise flushes that could hit RLS mid-transaction.
        factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
        return cls(engine=engine, session_factory=factory)

    @classmethod
    def from_settings(cls, settings: Settings) -> DatabaseSessionManager | None:
        """Build the APPLICATION-role manager from the pooled ``database_dsn``.

        Returns None when no database is configured, so the app can still serve
        health/liveness without a database (mirrors Phase 0 readiness behaviour).
        """
        dsn = settings.database_dsn
        if dsn is None:
            return None
        return cls.from_dsn(
            dsn,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
        )


def current_request_id() -> str:
    """The request id for audit rows, or '-' outside a request (e.g. a worker job)."""
    return request_id_var.get()


__all__ = [
    "DatabaseSessionManager",
    "current_request_id",
    "set_tenant_context",
]
