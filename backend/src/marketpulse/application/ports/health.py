"""Port: the contract every dependency health check must satisfy.

The application layer knows only this interface. Whether a check talks to PostgreSQL,
Redis, or a test double is an infrastructure detail (dependency inversion).
"""

from dataclasses import dataclass
from typing import Literal, Protocol

ProbeStatus = Literal["ok", "failed", "not_configured"]


@dataclass(frozen=True)
class ProbeResult:
    status: ProbeStatus
    latency_ms: float | None = None
    # Internal diagnostic only (for example an exception class name). It is logged,
    # never returned by public endpoints (blueprint 19.3).
    detail: str | None = None


class HealthProbe(Protocol):
    name: str
    required: bool  # True: failure makes the service not ready

    async def check(self) -> ProbeResult: ...
