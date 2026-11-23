"""Use case: is this instance ready to serve traffic?

Readiness is deliberately separate from liveness (blueprint 19.3):
- liveness  = "the process is running"; never touches dependencies, so a platform can poll it
  freely without waking a scale-to-zero database.
- readiness = "required dependencies are reachable"; may be slow, so poll it sparingly.
"""

import asyncio
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass

from marketpulse.application.ports.health import HealthProbe, ProbeResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CheckReport:
    name: str
    required: bool
    result: ProbeResult


@dataclass(frozen=True)
class ReadinessReport:
    checks: tuple[CheckReport, ...]

    @property
    def ready(self) -> bool:
        """Ready when every REQUIRED probe is ok. Optional probes are informational."""
        return all(c.result.status == "ok" for c in self.checks if c.required)


class ReadinessService:
    def __init__(self, probes: Sequence[HealthProbe], timeout_seconds: float) -> None:
        self._probes = tuple(probes)
        self._timeout_seconds = timeout_seconds

    async def check(self) -> ReadinessReport:
        # Probes run concurrently so total latency is the slowest probe, not the sum.
        reports = await asyncio.gather(*(self._run(probe) for probe in self._probes))
        return ReadinessReport(checks=tuple(reports))

    async def _run(self, probe: HealthProbe) -> CheckReport:
        started = time.perf_counter()
        try:
            result = await asyncio.wait_for(probe.check(), timeout=self._timeout_seconds)
        except TimeoutError:
            result = ProbeResult("failed", detail="timeout")
        except Exception as exc:  # a buggy probe must not take the endpoint down
            result = ProbeResult("failed", detail=type(exc).__name__)
        if result.status == "failed":
            logger.warning(
                "readiness probe failed: name=%s detail=%s elapsed_ms=%.0f",
                probe.name,
                result.detail,
                (time.perf_counter() - started) * 1000,
            )
        return CheckReport(name=probe.name, required=probe.required, result=result)
