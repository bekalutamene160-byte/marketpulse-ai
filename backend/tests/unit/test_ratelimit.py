"""Unit tests for the fixed-window rate limiter (blueprint 14.2 sign-in limiting)."""

from __future__ import annotations

import pytest

from marketpulse.core.ratelimit import FixedWindowRateLimiter


def test_allows_up_to_the_budget_then_rejects_within_the_window() -> None:
    limiter = FixedWindowRateLimiter(max_attempts=3, window_seconds=60)
    assert limiter.hit("login:1.2.3.4", now=0.0)
    assert limiter.hit("login:1.2.3.4", now=1.0)
    assert limiter.hit("login:1.2.3.4", now=2.0)
    assert not limiter.hit("login:1.2.3.4", now=3.0)  # over budget
    assert limiter.hit("login:5.6.7.8", now=3.0)  # another key is independent


def test_the_window_resets_after_it_elapses() -> None:
    limiter = FixedWindowRateLimiter(max_attempts=2, window_seconds=60)
    assert limiter.hit("k", now=0.0)
    assert limiter.hit("k", now=1.0)
    assert not limiter.hit("k", now=2.0)
    assert limiter.hit("k", now=61.0)  # window fully elapsed: fresh budget
    assert limiter.hit("k", now=61.5)
    assert not limiter.hit("k", now=62.0)


def test_rejections_do_not_extend_the_window() -> None:
    limiter = FixedWindowRateLimiter(max_attempts=1, window_seconds=10)
    assert limiter.hit("k", now=0.0)
    assert not limiter.hit("k", now=5.0)
    # The window started at t=0: it rolls over at t=10, rejections do not push it.
    assert limiter.hit("k", now=10.0)


def test_invalid_configuration_is_rejected() -> None:
    with pytest.raises(ValueError):
        FixedWindowRateLimiter(max_attempts=0, window_seconds=60)
    with pytest.raises(ValueError):
        FixedWindowRateLimiter(max_attempts=1, window_seconds=0)
