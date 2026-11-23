"""Adapter tests that need no running services: unconfigured and unreachable cases.

The success paths need real PostgreSQL/Redis and live in tests/integration.
"""

from marketpulse.infrastructure.db.probe import PostgresProbe
from marketpulse.infrastructure.queue.probe import RedisProbe


async def test_postgres_probe_not_configured() -> None:
    assert (await PostgresProbe(None, 1).check()).status == "not_configured"


async def test_postgres_probe_reports_failure_without_leaking_credentials() -> None:
    # Port 1 on localhost refuses the connection immediately.
    probe = PostgresProbe("postgresql://appuser:topsecretpw@127.0.0.1:1/db", timeout_seconds=2)
    result = await probe.check()
    assert result.status == "failed"
    assert result.detail is not None
    assert "topsecretpw" not in result.detail
    assert "127.0.0.1" not in result.detail  # class name only, never the driver message


async def test_redis_probe_not_configured() -> None:
    assert (await RedisProbe(None, 1).check()).status == "not_configured"


async def test_redis_probe_reports_failure_without_leaking_credentials() -> None:
    result = await RedisProbe("redis://:topsecretpw@127.0.0.1:1/0", timeout_seconds=2).check()
    assert result.status == "failed"
    assert result.detail is not None
    assert "topsecretpw" not in result.detail


def test_probe_required_defaults_match_the_architecture() -> None:
    # PostgreSQL is the system of record; Redis is only transport (ADR-002, ADR-003).
    assert PostgresProbe(None, 1).required is True
    assert RedisProbe(None, 1).required is False
