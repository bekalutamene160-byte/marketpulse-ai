"""SQLAlchemy implementations of the repository ports.

Each repository wraps a ``Session`` and maps between ORM rows and the pure domain
entities in ``marketpulse.domain.entities``. The session is opened and tenant-scoped
by the API dependency (application role) or the privileged provisioning path (owner
role); a repository never opens its own transaction and never reads a hidden tenant
global. Tenant filtering is done TWICE on every read: by the explicit
``organization_id`` predicate here, and by the database's row-level security policy
(ADR-0022). Either alone is a defense; a missed WHERE or a buggy predicate cannot
cross tenants because RLS rejects the row at the database.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from marketpulse.domain.entities import (
    AuditEvent,
    Membership,
    MemberSummary,
    Organization,
    User,
    Workspace,
)
from marketpulse.domain.tenancy import MembershipStatus, Role, UserStatus
from marketpulse.infrastructure.db.models import (
    AuditEventORM,
    MembershipORM,
    OrganizationORM,
    UserORM,
    WorkspaceORM,
)


# --- ORM -> domain entity mappers ---
def _to_organization(row: OrganizationORM) -> Organization:
    return Organization(
        id=row.id,
        slug=row.slug,
        display_name=row.display_name,
        default_market=row.default_market,
        timezone=row.timezone,
        base_currency=row.base_currency,
        is_demo=row.is_demo,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_workspace(row: WorkspaceORM) -> Workspace:
    return Workspace(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        is_read_only=row.is_read_only,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_user(row: UserORM) -> User:
    return User(
        id=row.id,
        email=row.email,
        status=UserStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_membership(row: MembershipORM) -> Membership:
    return Membership(
        id=row.id,
        organization_id=row.organization_id,
        user_id=row.user_id,
        role=Role(row.role),
        status=MembershipStatus(row.status),
        created_at=row.created_at,
    )


def _to_audit_event(row: AuditEventORM) -> AuditEvent:
    return AuditEvent(
        id=row.id,
        organization_id=row.organization_id,
        actor_user_id=row.actor_user_id,
        action=row.action,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        occurred_at=row.occurred_at,
        request_id=row.request_id,
        metadata=dict(row.metadata_),
    )


# --- repositories ---
class SqlAlchemyOrganizationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, org: Organization) -> None:
        self._session.add(
            OrganizationORM(
                id=org.id,
                slug=org.slug,
                display_name=org.display_name,
                default_market=org.default_market,
                timezone=org.timezone,
                base_currency=org.base_currency,
                is_demo=org.is_demo,
                created_at=org.created_at,
                updated_at=org.updated_at,
            )
        )

    def get(self, org_id: uuid.UUID) -> Organization | None:
        # session.get issues SELECT ... WHERE id = ?; RLS filters it for the app role.
        row = self._session.get(OrganizationORM, org_id)
        return _to_organization(row) if row is not None else None

    def get_by_slug(self, slug: str) -> Organization | None:
        row = self._session.execute(
            select(OrganizationORM).where(OrganizationORM.slug == slug)
        ).scalar_one_or_none()
        return _to_organization(row) if row is not None else None

    def list_by_ids(self, org_ids: list[uuid.UUID]) -> list[Organization]:
        if not org_ids:
            return []
        rows = (
            self._session.execute(select(OrganizationORM).where(OrganizationORM.id.in_(org_ids)))
            .scalars()
            .all()
        )
        # Keep the caller's order so /auth/me matches the membership ordering.
        by_id = {row.id: _to_organization(row) for row in rows}
        return [by_id[org_id] for org_id in org_ids if org_id in by_id]


class SqlAlchemyWorkspaceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, workspace: Workspace) -> None:
        self._session.add(
            WorkspaceORM(
                id=workspace.id,
                organization_id=workspace.organization_id,
                name=workspace.name,
                is_read_only=workspace.is_read_only,
                created_at=workspace.created_at,
                updated_at=workspace.updated_at,
            )
        )

    def get(self, workspace_id: uuid.UUID, org_id: uuid.UUID) -> Workspace | None:
        row = self._session.execute(
            select(WorkspaceORM).where(
                WorkspaceORM.id == workspace_id,
                WorkspaceORM.organization_id == org_id,
            )
        ).scalar_one_or_none()
        return _to_workspace(row) if row is not None else None

    def list_for_organization(self, org_id: uuid.UUID) -> list[Workspace]:
        rows = (
            self._session.execute(
                select(WorkspaceORM)
                .where(WorkspaceORM.organization_id == org_id)
                .order_by(WorkspaceORM.created_at.desc())
            )
            .scalars()
            .all()
        )
        return [_to_workspace(r) for r in rows]


class SqlAlchemyUserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, user: User, password_hash: str) -> None:
        self._session.add(
            UserORM(
                id=user.id,
                email=user.email,
                password_hash=password_hash,
                status=user.status.value,
                created_at=user.created_at,
                updated_at=user.updated_at,
            )
        )

    def get(self, user_id: uuid.UUID) -> User | None:
        # users is global (no RLS); Phase 1 never exposes it through the app API.
        row = self._session.get(UserORM, user_id)
        return _to_user(row) if row is not None else None

    def get_by_email(self, email: str) -> User | None:
        row = self._session.execute(
            select(UserORM).where(UserORM.email == email.lower())
        ).scalar_one_or_none()
        return _to_user(row) if row is not None else None


class SqlAlchemyMembershipRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, membership: Membership) -> None:
        self._session.add(
            MembershipORM(
                id=membership.id,
                organization_id=membership.organization_id,
                user_id=membership.user_id,
                role=membership.role.value,
                status=membership.status.value,
                created_at=membership.created_at,
            )
        )

    def list_for_organization(self, org_id: uuid.UUID) -> list[Membership]:
        rows = (
            self._session.execute(
                select(MembershipORM)
                .where(MembershipORM.organization_id == org_id)
                .order_by(MembershipORM.created_at.desc())
            )
            .scalars()
            .all()
        )
        return [_to_membership(r) for r in rows]

    def list_for_user(self, user_id: uuid.UUID) -> list[Membership]:
        # The request transaction already set app.user_id (set_tenant_context), so
        # the per-user policy (0002) makes this user's rows visible across orgs.
        rows = (
            self._session.execute(
                select(MembershipORM)
                .where(MembershipORM.user_id == user_id)
                .order_by(MembershipORM.created_at.asc())
            )
            .scalars()
            .all()
        )
        return [_to_membership(r) for r in rows]

    def list_members_with_users(self, org_id: uuid.UUID) -> list[MemberSummary]:
        rows = self._session.execute(
            select(MembershipORM, UserORM)
            .join(UserORM, UserORM.id == MembershipORM.user_id)
            .where(MembershipORM.organization_id == org_id)
            .order_by(MembershipORM.created_at.asc())
        ).all()
        return [
            MemberSummary(
                membership_id=membership.id,
                user_id=membership.user_id,
                email=user.email,
                role=Role(membership.role),
                status=MembershipStatus(membership.status),
                created_at=membership.created_at,
            )
            for membership, user in rows
        ]


class SqlAlchemyAuditEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_organization(self, org_id: uuid.UUID, *, limit: int = 100) -> list[AuditEvent]:
        rows = (
            self._session.execute(
                select(AuditEventORM)
                .where(AuditEventORM.organization_id == org_id)
                .order_by(AuditEventORM.occurred_at.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [_to_audit_event(r) for r in rows]
