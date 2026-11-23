"""Use case: read the current organization (the tenant root).

Phase 1 exposes only a read of the current tenant. Creating organizations is an
admin/bootstrap concern handled by ``TenantProvisioningService`` against a
privileged connection, NOT a self-service tenant endpoint (blueprint 14.1 notes the
route list is a contract, not a permission to expose every operation to every role).
Self-service signup is a Phase 2 product decision.

The repository is asked for the current tenant's id; row-level security is the
defense in depth that hides any row that does not match the session's
``app.tenant_id`` (ADR-0022). A ``None`` here means RLS already filtered it (or the
id is wrong) and we return 404 rather than revealing which.
"""

from __future__ import annotations

from marketpulse.application.ports.repositories import OrganizationRepository
from marketpulse.core.errors import AppError, ErrorCode
from marketpulse.core.tenancy import TenantContext
from marketpulse.domain.entities import Organization


class OrganizationService:
    def __init__(self, orgs: OrganizationRepository) -> None:
        self._orgs = orgs

    def get_current(self, ctx: TenantContext) -> Organization:
        org = self._orgs.get(ctx.organization_id)
        if org is None:
            raise AppError(
                ErrorCode.NOT_FOUND,
                "Organization was not found.",
                status_code=404,
                diagnostic=f"organization {ctx.organization_id} not visible to tenant context",
            )
        return org
