"""PostgreSQL health probe (adapter for the HealthProbe port).

Uses synchronous psycopg inside a worker thread on purpose: psycopg's async mode refuses to
run on Windows' default ProactorEventLoop, and the developer machine is Windows. A thread
works on every OS. The session layer chosen in Phase 1 must decide this question properly.
"""

import asyncio
import math
import time

import psycopg

from marketpulse.application.ports.health import ProbeResult


class PostgresProbe:
    name = "database"

    def __init__(self, dsn: str | None, timeout_seconds: float, *, required: bool = True) -> None:
        self._dsn = dsn
        self._timeout_seconds = timeout_seconds
        self.required = required

    async def check(self) -> ProbeResult:
        if self._dsn is None:
            return ProbeResult("not_configured")
        started = time.perf_counter()
        try:
            await asyncio.to_thread(self._ping)
        except Exception as exc:
            # Only the class name is kept: driver messages can contain hostnames or users.
            return ProbeResult("failed", detail=type(exc).__name__)
        return ProbeResult("ok", latency_ms=round((time.perf_counter() - started) * 1000, 1))

    def _ping(self) -> None:
        assert self._dsn is not None  # noqa: S101 - narrowed by check()
        with psycopg.connect(self._dsn, connect_timeout=math.ceil(self._timeout_seconds)) as conn:
            conn.execute("SELECT 1").fetchone()
