"""Audit event endpoints (Phase 1).

A thin read-through of the current tenant's audit trail. The repository runs against
the tenant-scoped session (``app.tenant_id`` is set, RLS filters), so only this
tenant's events are ever returned. ``limit`` is bounded to protect the database from
unbounded scans. Writes happen inside the use cases that cause the audited action
(``WorkspaceService.create`` etc.), not through this endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from marketpulse.api.deps import AuditEventRepositoryDep, TenantContextDep
from marketpulse.api.v1.schemas.tenancy import AuditEventResponse

router = APIRouter(prefix="/audit-events", tags=["tenancy"])


@router.get("", response_model=list[AuditEventResponse])
def list_audit_events(
    ctx: TenantContextDep,
    repo: AuditEventRepositoryDep,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[AuditEventResponse]:
    events = repo.list_for_organization(ctx.organization_id, limit=limit)
    return [AuditEventResponse.model_validate(e) for e in events]
