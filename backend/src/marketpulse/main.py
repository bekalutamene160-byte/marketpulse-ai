"""Composition root: the single place concrete adapters are wired to the application.

Run locally from the backend folder:

    uv run uvicorn marketpulse.main:create_app --factory --reload

``--factory`` makes uvicorn call ``create_app()`` itself, so importing this module
has no side effects (no settings read, no logging configured, no engine created).
That keeps tests and tooling predictable.

Phase 2 wires the authentication slice: a PRIVILEGED manager (direct URL, owner
role) used only by the signup path, the auth-backed session tenant resolver
(replacing the dev header as the default), and the fixed-window rate limiter for
login/register. The dev header resolver stays available for local/test tooling
behind the explicit ``MP_ENABLE_DEV_TENANT_HEADER`` flag (ADR-0024). With no
database configured the resolver is ``None`` and every tenant-scoped endpoint fails
closed with 401 — in staging/production ``Settings`` already refuses the dev header,
so there is no tenant path that bypasses authentication.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from marketpulse import __version__
from marketpulse.api.error_handlers import register_error_handlers
from marketpulse.api.middleware import REQUEST_ID_HEADER, RequestContextMiddleware
from marketpulse.api.v1.router import api_router
from marketpulse.application.ports.tenancy import TenantContextResolver
from marketpulse.application.services.readiness import ReadinessService
from marketpulse.config import Settings, get_settings
from marketpulse.core.clock import Clock, SystemClock
from marketpulse.core.logging import configure_logging
from marketpulse.core.ratelimit import FixedWindowRateLimiter
from marketpulse.infrastructure.db.probe import PostgresProbe
from marketpulse.infrastructure.db.session import DatabaseSessionManager
from marketpulse.infrastructure.queue.probe import RedisProbe
from marketpulse.infrastructure.tenancy.header_resolver import HeaderTenantContextResolver
from marketpulse.infrastructure.tenancy.session_resolver import SessionTenantContextResolver

logger = logging.getLogger("marketpulse")


def create_app(
    settings: Settings | None = None,
    readiness_service: ReadinessService | None = None,
    db_manager: DatabaseSessionManager | None = None,
    priv_db_manager: DatabaseSessionManager | None = None,
    tenant_resolver: TenantContextResolver | None = None,
    clock: Clock | None = None,
) -> FastAPI:
    """Build the application. Every argument exists so tests can inject doubles.

    Leave an argument unset to build its default from ``settings``: the DB manager
    from the pooled URL (``None`` when no database is configured), the PRIVILEGED
    manager from the direct URL (``None`` when absent — signup reports 503), the
    tenant resolver (session-backed when a database exists; dev header only where
    the flag allows it), the rate limiter, and the system clock.
    """
    settings = settings or get_settings()
    configure_logging(
        settings.log_level, settings.log_json, "marketpulse-api", settings.environment
    )

    if readiness_service is None:
        readiness_service = ReadinessService(
            probes=[
                PostgresProbe(settings.database_dsn, settings.probe_timeout_seconds, required=True),
                RedisProbe(settings.redis_dsn, settings.probe_timeout_seconds, required=False),
            ],
            # A little above the probe's own timeout so probes report their own failures first.
            timeout_seconds=settings.probe_timeout_seconds + 2,
        )

    if clock is None:
        clock = SystemClock()
    # Build defaults from settings only when the caller did not inject one.
    if db_manager is None:
        db_manager = DatabaseSessionManager.from_settings(settings)
    if priv_db_manager is None and settings.database_direct_dsn is not None:
        # The direct URL connects as the OWNER (bypasses RLS): signup only, never
        # tenant-scoped request work (ADR-0023).
        priv_db_manager = DatabaseSessionManager.from_dsn(settings.database_direct_dsn)
    if tenant_resolver is None:
        if settings.enable_dev_tenant_header:
            # Dev/test tooling only; Settings refuses this outside local/test.
            tenant_resolver = HeaderTenantContextResolver()
        elif db_manager is not None:
            # Real authentication: cookie -> session row -> tenant context.
            tenant_resolver = SessionTenantContextResolver(db_manager.session_factory, clock)
        else:
            tenant_resolver = None
    rate_limiter = FixedWindowRateLimiter(
        max_attempts=settings.auth_rate_limit_attempts,
        window_seconds=settings.auth_rate_limit_window_seconds,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "starting marketpulse-api v%s environment=%s", __version__, settings.environment
        )
        yield
        # Release the connection pools cleanly on shutdown (Neon returns pooled conns).
        if db_manager is not None:
            db_manager.dispose()
        if priv_db_manager is not None:
            priv_db_manager.dispose()
        logger.info("shutting down marketpulse-api")

    is_production = settings.environment == "production"
    app = FastAPI(
        title="MarketPulse AI API",
        version=__version__,
        lifespan=lifespan,
        # Do not advertise the API surface in production.
        docs_url=None if is_production else "/docs",
        redoc_url=None,
        openapi_url=None if is_production else "/openapi.json",
    )
    app.state.settings = settings
    app.state.readiness_service = readiness_service
    app.state.db_manager = db_manager
    app.state.priv_db_manager = priv_db_manager
    app.state.tenant_resolver = tenant_resolver
    app.state.clock = clock
    app.state.auth_rate_limiter = rate_limiter

    # The LAST middleware added is the OUTERMOST: request IDs wrap everything, CORS included.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER],
    )
    app.add_middleware(RequestContextMiddleware)

    register_error_handlers(app)
    app.include_router(api_router)  # versioned prefix: /api/v2 can coexist later
    return app


__all__ = ["create_app"]
