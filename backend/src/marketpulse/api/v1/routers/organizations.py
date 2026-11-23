"""Organization endpoints (Phase 1).

Only the current-tenant read is exposed. Creating organizations is an admin/bootstrap
concern (``TenantProvisioningService`` against a privileged connection), not a
self-service endpoint: the blueprint route list (14.1) is a contract, not permission
to expose every operation to every role. Self-service signup is a Phase 2 product
decision that will sit behind authentication and authorization.

The endpoint is a sync ``def``: FastAPI runs sync endpoints in Starlette's
threadpool, which is exactly what synchronous SQLAlchemy needs (ADR-0021).
"""

from __future__ import annotations

from fastapi import APIRouter

from marketpulse.api.deps import OrganizationServiceDep, TenantContextDep
from marketpulse.api.v1.schemas.tenancy import OrganizationResponse

router = APIRouter(prefix="/organizations", tags=["tenancy"])


@router.get("/current", response_model=OrganizationResponse)
def get_current_organization(
    ctx: TenantContextDep, svc: OrganizationServiceDep
) -> OrganizationResponse:
    org = svc.get_current(ctx)
    return OrganizationResponse.model_validate(org)
