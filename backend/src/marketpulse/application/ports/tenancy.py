"""Port: how the application learns the tenant context for a request or job.

The application NEVER trusts a client-supplied ``organization_id``. It asks a
resolver, which in production reads an authenticated session (Phase 2) and in
local/test reads a dev-only header (ADR-0024). The port takes a header mapping
rather than a Starlette ``Request`` so the application layer stays free of web
frameworks (blueprint 5.4).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from marketpulse.core.tenancy import TenantContext


class TenantContextResolver(Protocol):
    def resolve(self, headers: Mapping[str, str]) -> TenantContext | None: ...
