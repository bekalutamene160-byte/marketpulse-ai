"""Ports: repository contracts the application use cases rely on.

Every method operates on the pure domain entities in ``marketpulse.domain.entities``
and on primitive ids. No SQLAlchemy type appears here, so a use case is testable with
a fake repository in milliseconds and the persistence layer can be swapped without
touching business logic (blueprint 5.4 dependency inversion).

The tenant id is an explicit argument on every read: a repository never invents the
tenant from a hidden global. In production the row-level security policy is the
defense in depth that enforces this even if a repository is misused (ADR-0022).
"""

from __future__ import annotations

import uuid
from typing import Protocol

from marketpulse.domain.entities import (
    AuditEvent,
    Membership,
    MemberSummary,
    Organization,
    User,
    Workspace,
)


class OrganizationRepository(Protocol):
    def add(self, org: Organization) -> None: ...
    def get(self, org_id: uuid.UUID) -> Organization | None: ...
    def get_by_slug(self, slug: str) -> Organization | None: ...

    def list_by_ids(self, org_ids: list[uuid.UUID]) -> list[Organization]:
        """Batched read of organizations by id (Phase 2 ``/auth/me``).

        Visibility is still entirely RLS-governed: the per-user policy (0002) shows
        the organizations the session's user belongs to, the tenant policy shows the
        active one; missing/forbidden ids simply come back absent.
        """
        ...


class WorkspaceRepository(Protocol):
    def add(self, workspace: Workspace) -> None: ...
    def get(self, workspace_id: uuid.UUID, org_id: uuid.UUID) -> Workspace | None: ...
    def list_for_organization(self, org_id: uuid.UUID) -> list[Workspace]: ...


class UserRepository(Protocol):
    def add(self, user: User, password_hash: str) -> None: ...
    def get(self, user_id: uuid.UUID) -> User | None: ...
    def get_by_email(self, email: str) -> User | None: ...


class MembershipRepository(Protocol):
    def add(self, membership: Membership) -> None: ...
    def list_for_organization(self, org_id: uuid.UUID) -> list[Membership]: ...

    def list_for_user(self, user_id: uuid.UUID) -> list[Membership]:
        """ALL of one user's memberships (Phase 2 ``/auth/me``).

        The tenant-scoped session sets BOTH GUCs (``app.tenant_id`` AND
        ``app.user_id``), so the per-user RLS policy (migration 0002, ADR-0026)
        reveals this user's rows across organizations — and nothing else. Ordered
        oldest-first for a deterministic default organization.
        """
        ...

    def list_members_with_users(self, org_id: uuid.UUID) -> list[MemberSummary]:
        """The current tenant's member list (Phase 2 ``/organizations/members``).

        Joins memberships with users INSIDE the RLS-scoped read: only members of
        YOUR organization are ever returned, satisfying the Phase 1 invariant that
        ``users`` is never enumerated cross-tenant.
        """
        ...


class AuditEventRepository(Protocol):
    def list_for_organization(self, org_id: uuid.UUID, *, limit: int = 100) -> list[AuditEvent]: ...
