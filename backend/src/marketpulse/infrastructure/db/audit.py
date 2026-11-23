"""SqlAlchemyAuditWriter: persists audit rows within the caller's transaction.

Implements the ``AuditEventWriter`` port. The session is the caller's (opened by the
API dependency or the privileged provisioning path), so the audit INSERT commits
atomically with the business change it records — a crash between "create workspace"
and "write audit" cannot leave one without the other, because they share a
transaction (blueprint 7.4, ADR-004 thinking).

The row's ``organization_id`` is taken from the explicit ``ctx`` argument, never
from a hidden global. Under the application role, RLS ``WITH CHECK`` then verifies
that this ``organization_id`` equals the session's ``app.tenant_id``; under the
privileged provisioning role RLS is bypassed, so provisioning can record an audit
event for a brand-new org whose context is being established.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from marketpulse.core.ids import new_id
from marketpulse.core.tenancy import TenantContext
from marketpulse.domain.audit import AuditAction
from marketpulse.infrastructure.db.models import AuditEventORM
from marketpulse.infrastructure.db.session import current_request_id


class SqlAlchemyAuditWriter:
    def __init__(self, session: Session) -> None:
        self._session = session

    def write(
        self,
        *,
        ctx: TenantContext,
        action: AuditAction,
        entity_type: str,
        entity_id: uuid.UUID,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._session.add(
            AuditEventORM(
                id=new_id(),
                organization_id=ctx.organization_id,
                actor_user_id=ctx.user_id,
                action=action.value,
                entity_type=entity_type,
                entity_id=entity_id,
                request_id=current_request_id(),
                metadata_=metadata or {},
            )
        )
