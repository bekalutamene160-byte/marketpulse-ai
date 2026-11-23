"""Redis health probe (adapter for the HealthProbe port).

Redis is only the job transport (blueprint ADR-003), so by default this probe is NOT
required for API readiness: the API can serve reads without it. Only job dispatch needs it.
"""

import asyncio
import time

import redis

from marketpulse.application.ports.health import ProbeResult


class RedisProbe:
    name = "redis"

    def __init__(self, url: str | None, timeout_seconds: float, *, required: bool = False) -> None:
        self._url = url
        self._timeout_seconds = timeout_seconds
        self.required = required

    async def check(self) -> ProbeResult:
        if self._url is None:
            return ProbeResult("not_configured")
        started = time.perf_counter()
        try:
            await asyncio.to_thread(self._ping)
        except Exception as exc:
            return ProbeResult("failed", detail=type(exc).__name__)
        return ProbeResult("ok", latency_ms=round((time.perf_counter() - started) * 1000, 1))

    def _ping(self) -> None:
        assert self._url is not None  # noqa: S101 - narrowed by check()
        client = redis.Redis.from_url(
            self._url,
            socket_connect_timeout=self._timeout_seconds,
            socket_timeout=self._timeout_seconds,
        )
        try:
            client.ping()
        finally:
            client.close()
