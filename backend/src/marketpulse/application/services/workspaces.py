"""Use cases for workspaces within the current tenant.

A workspace always belongs to the caller's organization, so ``create`` sets the
new row's ``organization_id`` to ``ctx.organization_id``. Row-level security's
``WITH CHECK`` policy then accepts the insert because the row's tenant matches the
session's ``app.tenant_id`` (ADR-0022). An attempt to create a workspace for a
different organization is rejected by RLS at the database, not by application code
alone, so a repository bug cannot cross tenants.

The service is testable with a fake repository and fake audit writer in
milliseconds; it never imports SQLAlchemy.
"""

from __future__ import annotations

from marketpulse.application.ports.repositories import WorkspaceRepository
from marketpulse.application.services.audit import AuditService
from marketpulse.core.clock import Clock
from marketpulse.core.errors import AppError, ErrorCode
from marketpulse.core.ids import new_id
from marketpulse.core.tenancy import TenantContext
from marketpulse.domain.audit import AuditAction
from marketpulse.domain.entities import Workspace


class WorkspaceService:
    def __init__(
        self,
        workspaces: WorkspaceRepository,
        audit: AuditService,
        clock: Clock,
    ) -> None:
        self._workspaces = workspaces
        self._audit = audit
        self._clock = clock

    def list_for_current(self, ctx: TenantContext) -> list[Workspace]:
        return self._workspaces.list_for_organization(ctx.organization_id)

    def create(
        self,
        *,
        ctx: TenantContext,
        name: str,
        is_read_only: bool = False,
    ) -> Workspace:
        name = name.strip()
        if not name or len(name) > 100:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "Workspace name must be 1 to 100 characters.",
                status_code=422,
                diagnostic=f"name length={len(name)}",
            )
        now = self._clock.utcnow()
        workspace = Workspace(
            id=new_id(),
            organization_id=ctx.organization_id,
            name=name,
            is_read_only=is_read_only,
            created_at=now,
            updated_at=now,
        )
        self._workspaces.add(workspace)
        self._audit.record(
            ctx=ctx,
            action=AuditAction.WORKSPACE_CREATED,
            entity_type="workspace",
            entity_id=workspace.id,
            metadata={"name": name, "is_read_only": is_read_only},
        )
        return workspace
