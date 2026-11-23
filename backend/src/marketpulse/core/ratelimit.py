"""Fixed-window rate limiting for authentication endpoints (blueprint 14.2).

Why: sign-in and signup are the two endpoints an attacker can hit without any
credential. Blueprint 14.2 requires rate limiting on sign-in; the same limiter
guards registration because registration creates tenants.

Scope and honesty: this is an IN-PROCESS, single-instance limiter. With one API
process (the Phase 2 deployment shape) it is exact. Behind multiple replicas the
budget is per-replica until the counters move to Redis — a deliberate Phase 2
simplification recorded in ADR-0025, upgraded when the durable queue phase (5)
introduces shared Redis infrastructure.

The window is a fixed bucket that resets every ``window_seconds``: after N attempts
within the window, further attempts are rejected until the window rolls over. Fixed
windows are simple, deterministic, and testable with an injected fake clock; sliding
windows are a later refinement, not a correctness need here.
"""

from __future__ import annotations

import threading


class FixedWindowRateLimiter:
    """Allow at most ``max_attempts`` keyed actions per ``window_seconds``."""

    def __init__(self, *, max_attempts: int, window_seconds: float) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._lock = threading.Lock()
        # key -> (window_start_epoch, attempts_in_window)
        self._buckets: dict[str, tuple[float, int]] = {}

    def hit(self, key: str, *, now: float) -> bool:
        """Record one attempt for ``key`` at ``now`` (epoch seconds).

        Returns True when the attempt is ALLOWED, False when the key is over its
        budget for the current window. The clock is an explicit argument so tests
        are deterministic and the limiter never reads a global time source.
        """
        with self._lock:
            start, count = self._buckets.get(key, (now, 0))
            if now - start >= self._window_seconds:
                # The old window has fully elapsed: start a fresh one with this hit.
                self._buckets[key] = (now, 1)
                return True
            if count >= self._max_attempts:
                return False
            self._buckets[key] = (start, count + 1)
            return True

    def reset(self) -> None:
        """Clear all counters (tests and admin tooling only)."""
        with self._lock:
            self._buckets.clear()


__all__ = ["FixedWindowRateLimiter"]
