"""Workspace endpoints (Phase 1).

List and create workspaces within the current tenant. ``create`` sets the new row's
``organization_id`` to the caller's tenant; row-level security's ``WITH CHECK``
policy then accepts the insert because the row's tenant matches the session's
``app.tenant_id`` (ADR-0022). A request that tried to create a workspace for another
tenant would be rejected at the database, not just by application code.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from marketpulse.api.deps import TenantContextDep, WorkspaceServiceDep
from marketpulse.api.v1.schemas.tenancy import CreateWorkspaceRequest, WorkspaceResponse

router = APIRouter(prefix="/workspaces", tags=["tenancy"])


@router.get("", response_model=list[WorkspaceResponse])
def list_workspaces(ctx: TenantContextDep, svc: WorkspaceServiceDep) -> list[WorkspaceResponse]:
    return [WorkspaceResponse.model_validate(w) for w in svc.list_for_current(ctx)]


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
def create_workspace(
    ctx: TenantContextDep,
    svc: WorkspaceServiceDep,
    body: CreateWorkspaceRequest,
) -> WorkspaceResponse:
    ws = svc.create(ctx=ctx, name=body.name, is_read_only=body.is_read_only)
    return WorkspaceResponse.model_validate(ws)
