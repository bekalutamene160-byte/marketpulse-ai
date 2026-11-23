"""Request-context middleware: request IDs and request logging.

Written as a pure ASGI middleware rather than Starlette's BaseHTTPMiddleware because it
behaves predictably with streaming responses, background tasks and exceptions.
"""

import logging
import re
import time
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from marketpulse.core.logging import request_id_var

logger = logging.getLogger("marketpulse.request")

REQUEST_ID_HEADER = "X-Request-ID"
# Only trust client-supplied IDs that look harmless. Logging arbitrary header text enables
# log injection (forged log lines, enormous payloads).
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get(REQUEST_ID_HEADER, "")
        request_id = incoming if _SAFE_ID.match(incoming) else uuid.uuid4().hex
        # Exposed as request.state.request_id so exception handlers can read it too.
        scope.setdefault("state", {})["request_id"] = request_id

        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status_code = 500  # what we report if an exception escapes before a response starts

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            logger.info(
                "%s %s -> %s in %.1f ms",
                scope["method"],
                scope["path"],
                status_code,
                (time.perf_counter() - started) * 1000,
            )
            request_id_var.reset(token)
