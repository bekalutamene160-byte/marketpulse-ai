"""Dramatiq worker entrypoint (a separate OS process from the API, blueprint ADR-001).

Run from the backend folder:

    uv run dramatiq marketpulse.worker.app --processes 1 --threads 2

Phase 0 only proves the worker can start, reach Redis, and execute a task. The durable
workflow tables, outbox dispatcher, retries and idempotency arrive in Phase 5.
"""

import logging

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from marketpulse.config import get_settings

logger = logging.getLogger("marketpulse.worker")

_settings = get_settings()
if _settings.redis_dsn is None:
    raise RuntimeError(
        "MP_REDIS_URL is not set: the worker cannot start without a Redis broker. "
        "See docs/DEPLOYMENT.md."
    )

# dramatiq ships no type hints for RedisBroker's constructor, so mypy strict flags the call.
broker = RedisBroker(url=_settings.redis_dsn)  # type: ignore[no-untyped-call]
dramatiq.set_broker(broker)


@dramatiq.actor(queue_name="default", max_retries=0)
def ping() -> None:
    """Smoke-test task proving API -> Redis -> worker plumbing end to end."""
    logger.info("ping task executed")
