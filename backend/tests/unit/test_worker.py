import importlib
import sys

import pytest

from marketpulse.config import get_settings


@pytest.fixture(autouse=True)
def _fresh_settings():  # type: ignore[no-untyped-def]
    get_settings.cache_clear()
    sys.modules.pop("marketpulse.worker.app", None)
    yield
    get_settings.cache_clear()
    sys.modules.pop("marketpulse.worker.app", None)


def test_worker_registers_the_ping_actor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MP_REDIS_URL", "redis://127.0.0.1:6379/0")
    module = importlib.import_module("marketpulse.worker.app")
    assert module.ping.actor_name == "ping"
    assert module.ping.queue_name == "default"


def test_worker_refuses_to_start_without_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    # A blank environment variable outranks a developer's .env and means "unset".
    monkeypatch.setenv("MP_REDIS_URL", "")
    with pytest.raises(RuntimeError, match="MP_REDIS_URL"):
        importlib.import_module("marketpulse.worker.app")
