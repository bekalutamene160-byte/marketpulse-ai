"""Dev/test tenant context resolver (ADR-0024, provisional).

Reads ``X-MP-Organization`` and optional ``X-MP-User`` / ``X-MP-Workspace`` headers
and returns a ``TenantContext``. This exists ONLY so the tenant-isolation machinery
can be exercised end to end before Phase 2 ships authentication. It trusts the
client, so it must never run where real tenants exist: the composition root refuses
to wire it in staging/production, and ``Settings._non_local_guardrails`` rejects
``enable_dev_tenant_header`` there. Phase 2 replaces this with an auth-backed
resolver that reads an authenticated session, never a client header.

Header values MUST be canonical UUIDs; anything else resolves to ``None`` (which
``TenantContextService`` turns into 401 UNAUTHORIZED). A malformed value is not
raised: returning ``None`` keeps the failure mode uniform and avoids telling a
probing client which header was wrong.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping

from marketpulse.core.ids import is_valid_uuid_str
from marketpulse.core.tenancy import TenantContext

_ORG_HEADER = "X-MP-Organization"
_USER_HEADER = "X-MP-User"
_WORKSPACE_HEADER = "X-MP-Workspace"


def _header(headers: Mapping[str, str], name: str) -> str | None:
    """Case-insensitive lookup. Starlette lowercases keys; raw mappings may not."""
    if name in headers:
        return headers[name]
    lower = name.lower()
    if lower in headers:
        return headers[lower]
    return None


class HeaderTenantContextResolver:
    def resolve(self, headers: Mapping[str, str]) -> TenantContext | None:
        org = _header(headers, _ORG_HEADER)
        if org is None or not is_valid_uuid_str(org):
            return None
        org_id = uuid.UUID(org)

        user_id: uuid.UUID | None = None
        user = _header(headers, _USER_HEADER)
        if user is not None and is_valid_uuid_str(user):
            user_id = uuid.UUID(user)

        workspace_id: uuid.UUID | None = None
        ws = _header(headers, _WORKSPACE_HEADER)
        if ws is not None and is_valid_uuid_str(ws):
            workspace_id = uuid.UUID(ws)

        return TenantContext(organization_id=org_id, workspace_id=workspace_id, user_id=user_id)
