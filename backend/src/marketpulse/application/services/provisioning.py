"""Use case: provision tenants, users and memberships (admin/bootstrap only).

This service runs against a PRIVILEGED session (the project owner role on the
direct, non-pooled connection), which bypasses row-level security. It is the only
path that creates organizations and users: the normal application role cannot,
because RLS on ``organizations`` requires the session's ``app.tenant_id`` to equal
the row's id, and a brand-new org's id cannot be the session context until the row
exists. Provisioning is therefore a platform/admin concern, never a self-service
tenant endpoint (ADR-0023).

Consumers: the app-role bootstrap script, integration tests that seed two tenants,
and (Phase 2+) an admin signup path behind an authorization check. It must never be
wired into the public API without verifying the caller is a platform administrator.
"""

from __future__ import annotations

import uuid

from marketpulse.application.ports.repositories import (
    MembershipRepository,
    OrganizationRepository,
    UserRepository,
)
from marketpulse.application.services.audit import AuditService
from marketpulse.core.clock import Clock
from marketpulse.core.errors import AppError, ErrorCode
from marketpulse.core.ids import new_id
from marketpulse.core.security import hash_password
from marketpulse.core.tenancy import TenantContext
from marketpulse.domain.audit import AuditAction
from marketpulse.domain.entities import Membership, Organization, User
from marketpulse.domain.tenancy import MembershipStatus, Role, UserStatus


class TenantProvisioningService:
    def __init__(
        self,
        orgs: OrganizationRepository,
        users: UserRepository,
        memberships: MembershipRepository,
        audit: AuditService,
        clock: Clock,
    ) -> None:
        self._orgs = orgs
        self._users = users
        self._memberships = memberships
        self._audit = audit
        self._clock = clock

    def create_organization(
        self,
        *,
        slug: str,
        display_name: str,
        default_market: str | None,
        timezone: str,
        base_currency: str,
        is_demo: bool = False,
    ) -> Organization:
        if self._orgs.get_by_slug(slug) is not None:
            raise AppError(
                ErrorCode.CONFLICT,
                "An organization with that slug already exists.",
                status_code=409,
                diagnostic=f"slug={slug}",
            )
        now = self._clock.utcnow()
        org = Organization(
            id=new_id(),
            slug=slug,
            display_name=display_name,
            default_market=default_market,
            timezone=timezone,
            base_currency=base_currency,
            is_demo=is_demo,
            created_at=now,
            updated_at=now,
        )
        self._orgs.add(org)
        # Audit under the new org's own context so the row is scoped to it from birth.
        ctx = TenantContext(organization_id=org.id)
        self._audit.record(
            ctx=ctx,
            action=AuditAction.ORGANIZATION_CREATED,
            entity_type="organization",
            entity_id=org.id,
            metadata={"slug": slug, "is_demo": is_demo},
        )
        return org

    def create_user(
        self,
        *,
        email: str,
        password: str,
        status: UserStatus = UserStatus.ACTIVE,
    ) -> User:
        email = email.strip().lower()
        if self._users.get_by_email(email) is not None:
            raise AppError(
                ErrorCode.CONFLICT,
                "A user with that email already exists.",
                status_code=409,
                diagnostic=f"email={email}",
            )
        now = self._clock.utcnow()
        user = User(id=new_id(), email=email, status=status, created_at=now, updated_at=now)
        # The hash is an infrastructure secret: it is written to the row but never
        # returned on the domain User (see domain/entities.py).
        self._users.add(user, hash_password(password))
        return user

    def add_membership(
        self,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        role: Role,
        status: MembershipStatus = MembershipStatus.ACTIVE,
    ) -> Membership:
        now = self._clock.utcnow()
        membership = Membership(
            id=new_id(),
            organization_id=organization_id,
            user_id=user_id,
            role=role,
            status=status,
            created_at=now,
        )
        self._memberships.add(membership)
        ctx = TenantContext(organization_id=organization_id, user_id=user_id)
        self._audit.record(
            ctx=ctx,
            action=AuditAction.MEMBERSHIP_ADDED,
            entity_type="membership",
            entity_id=membership.id,
            metadata={"role": role.value, "user_id": str(user_id)},
        )
        return membership
