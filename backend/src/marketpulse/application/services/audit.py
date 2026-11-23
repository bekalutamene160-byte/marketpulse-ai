"""Use case: record an audit event for the current tenant and actor.

The service is a thin, testable wrapper over the ``AuditEventWriter`` port. It
takes the tenant context explicitly (set by the API dependency per request) so the
audit row's ``organization_id`` is always provably the caller's tenant and never a
hidden global. The writer runs inside the caller's transaction, so the audit row
commits atomically with the business change (blueprint 7.4, ADR-004 thinking).
"""

from __future__ import annotations

import uuid
from typing import Any

from marketpulse.application.ports.audit import AuditEventWriter
from marketpulse.core.tenancy import TenantContext
from marketpulse.domain.audit import AuditAction


class AuditService:
    def __init__(self, writer: AuditEventWriter) -> None:
        self._writer = writer

    def record(
        self,
        *,
        ctx: TenantContext,
        action: AuditAction,
        entity_type: str,
        entity_id: uuid.UUID,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._writer.write(
            ctx=ctx,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata=metadata,
        )
