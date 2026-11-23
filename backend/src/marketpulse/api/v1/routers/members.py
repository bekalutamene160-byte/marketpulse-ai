"""Member list endpoint (Phase 2).

A thin tenant-scoped read of the current organization's members, powered by the
RLS-secured ``memberships -> users`` join. This satisfies the Phase 1 invariant: the
global ``users`` table is never enumerated — the join returns only the people who
belong to YOUR organization, filtered again by row-level security at the database.
Invitation creation is a later phase (no email adapter exists yet — ADR-012).
"""

from __future__ import annotations

from fastapi import APIRouter

from marketpulse.api.deps import MembershipRepositoryDep, TenantContextDep
from marketpulse.api.v1.schemas.auth import MemberResponse, member_responses

router = APIRouter(prefix="/organizations", tags=["tenancy"])


@router.get("/members", response_model=list[MemberResponse])
def list_members(
    ctx: TenantContextDep,
    memberships: MembershipRepositoryDep,
) -> list[MemberResponse]:
    summaries = memberships.list_members_with_users(ctx.organization_id)
    return member_responses(summaries)
