"""Shared fixtures.

A developer's real .env (with real Neon/Redis URLs) must never reach a unit test, so
tests build Settings explicitly: ``_env_file=None`` plus explicit ``None`` URLs,
which outrank anything in the environment.

Phase 1 adds a ``tenant_settings`` fixture that enables the dev header resolver
(allowed in ``test``) so the API tests can exercise tenant-context resolution and
the 401 path for real, plus a ``make_tenant_app`` builder that wires it into the app.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI

from marketpulse.application.services.readiness import ReadinessService
from marketpulse.config import Settings
from marketpulse.main import create_app
from tests.fakes import AnyProbe


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        log_level="WARNING",
        database_url=None,
        redis_url=None,
    )


@pytest.fixture
def make_app(settings: Settings) -> Callable[..., FastAPI]:
    def _make(*probes: AnyProbe) -> FastAPI:
        return create_app(settings, ReadinessService(probes, timeout_seconds=1))

    return _make


@pytest.fixture
def fixed_now() -> datetime:
    """A pinned UTC instant for deterministic created_at/occurred_at in tests."""
    return datetime(2026, 11, 20, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def tenant_settings() -> Settings:
    """Settings with the dev tenant header resolver enabled (allowed in test)."""
    return Settings(
        _env_file=None,
        environment="test",
        log_level="WARNING",
        database_url=None,
        redis_url=None,
        enable_dev_tenant_header=True,
    )


@pytest.fixture
def make_tenant_app(tenant_settings: Settings) -> Callable[..., FastAPI]:
    """Build an app whose tenant context comes from the real HeaderTenantContextResolver.

    Tests override the service dependencies (get_organization_service etc.) with fakes
    so no database is needed, while the tenant-resolution and 401 paths run for real.
    """

    def _make(*probes: AnyProbe) -> FastAPI:
        return create_app(tenant_settings, ReadinessService(probes, timeout_seconds=1))

    return _make
