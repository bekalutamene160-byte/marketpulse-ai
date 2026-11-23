"""Structured logging with request correlation IDs.

Why: once the API, workers and the agent all write logs, the first question in any
incident is "what happened during THIS request or run?". A correlation ID on every log
line turns that into a single search (blueprint section 16.3).
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

# A ContextVar holds a value that is isolated per async task, so concurrent requests never
# see each other's IDs. A plain module-level variable would be shared and wrong.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    """Attach the current request ID to every record unless one was set explicitly."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line: timestamp, severity, service, environment, IDs, message."""

    def __init__(self, service: str, environment: str) -> None:
        super().__init__()
        self._service = service
        self._environment = environment

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "severity": record.levelname,
            "service": self._service,
            "environment": self._environment,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(
    level: str, json_logs: bool, service: str = "marketpulse-api", environment: str = "local"
) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())
    if json_logs:
        handler.setFormatter(JsonFormatter(service, environment))
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s")
        )

    root = logging.getLogger()
    root.handlers.clear()  # calling this twice (e.g. --reload, tests) must not duplicate lines
    root.addHandler(handler)
    root.setLevel(level)

    # Our middleware logs each request with status, timing and request ID, so silence
    # uvicorn's own access log to avoid every request appearing twice.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
