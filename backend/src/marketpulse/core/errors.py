"""Stable application errors (blueprint 18.1).

Every error has a stable machine-readable code, a safe message for users, and an
optional internal diagnostic that is logged but never returned to clients.

Only the generic codes needed so far exist. Domain codes from blueprint 18.1
(SOURCE_ACCESS_DENIED, PRODUCT_MATCH_AMBIGUOUS, ...) are added in the phase that
first raises them, so no code exists without a producer and a test. Phase 1 adds
UNAUTHORIZED, FORBIDDEN and CONFLICT because tenant foundation work needs them:
no tenant context -> 401, tenant set but action not allowed -> 403, duplicate
slug/email -> 409.
"""

from enum import StrEnum


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    RATE_LIMITED = "RATE_LIMITED"  # Phase 2: auth endpoints (blueprint 14.2 sign-in limiting)
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    HTTP_ERROR = "HTTP_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(Exception):
    """Base class for errors that are safe to describe to the caller."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        status_code: int = 400,
        diagnostic: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message  # safe for clients
        self.status_code = status_code
        self.diagnostic = diagnostic  # internal only: logged, never serialized
