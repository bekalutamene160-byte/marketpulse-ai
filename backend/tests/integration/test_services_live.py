"""Connectivity checks against YOUR real PostgreSQL (Neon) and Redis.

Opt-in because they need real services and credentials:

    uv run pytest -m integration

Settings are read from the real environment / backend/.env on purpose. In CI these run
against throwaway Postgres and Redis service containers.
"""

import pytest

from marketpulse.config import Settings
from marketpulse.infrastructure.db.probe import PostgresProbe
from marketpulse.infrastructure.queue.probe import RedisProbe

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def live_settings() -> Settings:
    return Settings()


async def test_database_is_reachable(live_settings: Settings) -> None:
    if live_settings.database_dsn is None:
        pytest.skip("MP_DATABASE_URL is not set")
    # Generous timeout: a scale-to-zero database needs a moment to wake on the first call.
    result = await PostgresProbe(live_settings.database_dsn, timeout_seconds=30).check()
    assert result.status == "ok", f"database probe failed: {result.detail}"


async def test_redis_is_reachable(live_settings: Settings) -> None:
    if live_settings.redis_dsn is None:
        pytest.skip("MP_REDIS_URL is not set")
    result = await RedisProbe(live_settings.redis_dsn, timeout_seconds=30).check()
    assert result.status == "ok", f"redis probe failed: {result.detail}"
