"""Clock abstraction (blueprint 5.4: core/clock.py).

A single place to obtain "now" in UTC. Use cases take a ``Clock`` so tests can pin
time and assert ``created_at`` / ``occurred_at`` deterministically; production uses
the system clock. Never call ``datetime.now()`` directly inside a use case: it makes
the test non-deterministic and hides the time dependency.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def utcnow(self) -> datetime: ...


class SystemClock:
    """The production clock. Reads the monotonic system wall clock in UTC."""

    def utcnow(self) -> datetime:
        return datetime.now(UTC)


def utcnow() -> datetime:
    """Module-level convenience for non-injected callers (infrastructure only)."""
    return datetime.now(UTC)
