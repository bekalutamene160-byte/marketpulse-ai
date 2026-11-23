"""Use case: resolve and require the tenant context for the current operation.

Every tenant-scoped endpoint or job starts by asking this service for the context.
No context -> 401 UNAUTHORIZED (blueprint Phase 1 exit gate: "unauthorized access
returns correct errors"). The service delegates the actual resolution to the
``TenantContextResolver`` port, so production (Phase 2 auth) and local/test
(ADR-0024 dev header) plug in different resolvers without the use case knowing.
"""

from __future__ import annotations

from collections.abc import Mapping

from marketpulse.application.ports.tenancy import TenantContextResolver
from marketpulse.core.errors import AppError, ErrorCode
from marketpulse.core.tenancy import TenantContext


class TenantContextService:
    def __init__(self, resolver: TenantContextResolver | None = None) -> None:
        # resolver may be None in environments where no tenant source is configured
        # yet (e.g. local without the dev header, before Phase 2 auth). In that case
        # every resolve() is 401: fail closed rather than serve unscoped data.
        self._resolver = resolver

    def resolve(self, headers: Mapping[str, str]) -> TenantContext:
        if self._resolver is None:
            raise AppError(
                ErrorCode.UNAUTHORIZED,
                "Authentication is required to access this resource.",
                status_code=401,
                diagnostic="no tenant context resolver configured",
            )
        ctx = self._resolver.resolve(headers)
        if ctx is None:
            raise AppError(
                ErrorCode.UNAUTHORIZED,
                "Authentication is required to access this resource.",
                status_code=401,
                diagnostic="no tenant context resolved from the request",
            )
        return ctx
