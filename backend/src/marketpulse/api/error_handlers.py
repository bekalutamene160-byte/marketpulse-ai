"""One consistent error envelope for every failure (blueprint 14.2):

    {"error": {"code": "...", "message": "...", "request_id": "...", "details": [...]}}

Clients branch on the stable `code`; humans read `message`; support searches logs by
`request_id`. Internal diagnostics and exception text are logged, never returned.
"""

import logging
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from marketpulse.api.middleware import REQUEST_ID_HEADER
from marketpulse.core.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "-"))


def _response(
    request: Request,
    status_code: int,
    code: ErrorCode,
    message: str,
    details: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    request_id = _request_id(request)
    body: dict[str, Any] = {"code": code.value, "message": message, "request_id": request_id}
    if details:
        body["details"] = details
    # Exceptions that reach the outermost server middleware bypass our ASGI middleware, so the
    # header is set here as well.
    return JSONResponse(
        status_code=status_code, content={"error": body}, headers={REQUEST_ID_HEADER: request_id}
    )


async def _app_error(request: Request, exc: Exception) -> JSONResponse:
    error = cast(AppError, exc)
    if error.diagnostic:
        logger.warning("app error %s: %s", error.code.value, error.diagnostic)
    return _response(request, error.status_code, error.code, error.message)


async def _http_error(request: Request, exc: Exception) -> JSONResponse:
    error = cast(StarletteHTTPException, exc)
    code = ErrorCode.NOT_FOUND if error.status_code == 404 else ErrorCode.HTTP_ERROR
    message = error.detail if isinstance(error.detail, str) else "Request failed"
    return _response(request, error.status_code, code, message)


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    error = cast(RequestValidationError, exc)
    # Location, message and type only. Never echo the submitted `input` back to the client.
    details = [
        {"loc": [str(part) for part in e["loc"]], "msg": e["msg"], "type": e["type"]}
        for e in error.errors()
    ]
    return _response(request, 422, ErrorCode.VALIDATION_ERROR, "Request validation failed", details)


async def _unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled exception",
        exc_info=exc,
        extra={"request_id": _request_id(request)},
    )
    return _response(request, 500, ErrorCode.INTERNAL_ERROR, "An internal error occurred")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unhandled_error)
