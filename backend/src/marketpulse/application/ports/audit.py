"""Port: writing audit events within the caller's transaction.

The use case owns the semantics (what action, what entity); the adapter owns the
SQL. The writer runs inside the caller's open transaction so the audit row commits
atomically with the business change it describes (blueprint 7.4 ``audit_events``;
the same transactional-integrity thinking as the outbox in ADR-004, applied to
audit). ``ctx`` is passed explicitly: the writer never reads a hidden global for
the tenant, so the row's ``organization_id`` is always provably the caller's tenant.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from marketpulse.core.tenancy import TenantContext
from marketpulse.domain.audit import AuditAction


class AuditEventWriter(Protocol):
    def write(
        self,
        *,
        ctx: TenantContext,
        action: AuditAction,
        entity_type: str,
        entity_id: uuid.UUID,
        metadata: dict[str, Any] | None = None,
    ) -> None: ...
