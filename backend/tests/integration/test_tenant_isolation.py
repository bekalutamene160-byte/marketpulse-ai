"""Integration test: two tenants cannot see each other's data (Phase 1 exit gate).

Provision two organizations (each with a workspace and an audit event) as the owner,
then as the application role with tenant context set to A: assert A's rows are
visible and B's are invisible even when explicitly requested by id. Then switch the
context to B and assert the reverse. Row-level security is the defense that enforces
this; the explicit ``organization_id`` predicate in the repository is the first line.

    MP_DATABASE_URL=postgresql://marketpulse_app:pw@host/db \
    MP_DATABASE_DIRECT_URL=postgresql://owner:pw@host/db \
    uv run pytest -m integration tests/integration/test_tenant_isolation.py
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from marketpulse.application.services.audit import AuditService
from marketpulse.application.services.provisioning import TenantProvisioningService
from marketpulse.application.services.workspaces import WorkspaceService
from marketpulse.core.clock import SystemClock
from marketpulse.core.tenancy import TenantContext
from marketpulse.domain.tenancy import Role
from marketpulse.infrastructure.db.audit import SqlAlchemyAuditWriter
from marketpulse.infrastructure.db.repositories import (
    SqlAlchemyAuditEventRepository,
    SqlAlchemyMembershipRepository,
    SqlAlchemyOrganizationRepository,
    SqlAlchemyUserRepository,
    SqlAlchemyWorkspaceRepository,
)
from marketpulse.infrastructure.db.session import DatabaseSessionManager, set_tenant_context

pytestmark = pytest.mark.integration

SLUG_A = "iso-tenant-a"
SLUG_B = "iso-tenant-b"


def _provision(priv_mgr: DatabaseSessionManager) -> tuple[uuid.UUID, uuid.UUID]:
    session = priv_mgr.session_factory()
    try:
        with session.begin():
            orgs = SqlAlchemyOrganizationRepository(session)
            users = SqlAlchemyUserRepository(session)
            memberships = SqlAlchemyMembershipRepository(session)
            audit = AuditService(SqlAlchemyAuditWriter(session))
            provisioning = TenantProvisioningService(orgs, users, memberships, audit, SystemClock())
            org_a = provisioning.create_organization(
                slug=SLUG_A,
                display_name="Tenant A",
                default_market="US",
                timezone="UTC",
                base_currency="USD",
            )
            org_b = provisioning.create_organization(
                slug=SLUG_B,
                display_name="Tenant B",
                default_market="US",
                timezone="UTC",
                base_currency="USD",
            )
            user_a = provisioning.create_user(email="a@iso.test", password="pw-a")
            provisioning.add_membership(
                organization_id=org_a.id, user_id=user_a.id, role=Role.OWNER
            )
            workspaces = WorkspaceService(
                SqlAlchemyWorkspaceRepository(session),
                AuditService(SqlAlchemyAuditWriter(session)),
                SystemClock(),
            )
            workspaces.create(ctx=TenantContext(organization_id=org_a.id), name="A-ws")
            workspaces.create(ctx=TenantContext(organization_id=org_b.id), name="B-ws")
            return org_a.id, org_b.id
    finally:
        session.close()


def _cleanup(priv_mgr: DatabaseSessionManager) -> None:
    session = priv_mgr.session_factory()
    try:
        with session.begin():
            # Deleting the organizations cascades (ondelete=CASCADE) to their
            # memberships, workspaces and audit events; the membership rows must be
            # gone before the user itself can go. Deleting the user too makes this
            # test idempotent: a second run would otherwise hit the unique-email
            # CONFLICT in create_user.
            session.execute(
                text("DELETE FROM organizations WHERE slug IN (:a, :b)"),
                {"a": SLUG_A, "b": SLUG_B},
            )
            session.execute(
                text("DELETE FROM users WHERE email = :email"),
                {"email": "a@iso.test"},
            )
    finally:
        session.close()


def _visible_workspaces(app_mgr: DatabaseSessionManager, ctx: TenantContext) -> list[str]:
    session = app_mgr.session_factory()
    try:
        with session.begin():
            set_tenant_context(session, ctx)
            repo = SqlAlchemyWorkspaceRepository(session)
            return [w.name for w in repo.list_for_organization(ctx.organization_id)]
    finally:
        session.close()


def _visible_audit_events(app_mgr: DatabaseSessionManager, ctx: TenantContext) -> int:
    session = app_mgr.session_factory()
    try:
        with session.begin():
            set_tenant_context(session, ctx)
            repo = SqlAlchemyAuditEventRepository(session)
            return len(repo.list_for_organization(ctx.organization_id, limit=50))
    finally:
        session.close()


def test_two_tenants_are_isolated(migrated_schema: str, app_role_dsn: str) -> None:
    priv_mgr = DatabaseSessionManager.from_dsn(migrated_schema, pool_size=2, max_overflow=0)
    app_mgr = DatabaseSessionManager.from_dsn(app_role_dsn, pool_size=2, max_overflow=0)
    try:
        org_a, org_b = _provision(priv_mgr)
        try:
            ctx_a = TenantContext(organization_id=org_a)
            ctx_b = TenantContext(organization_id=org_b)

            # Under A's context: A's workspace visible, B's invisible.
            assert _visible_workspaces(app_mgr, ctx_a) == ["A-ws"]
            # Even explicitly asking for B's org under A's context returns nothing (RLS).
            session = app_mgr.session_factory()
            try:
                with session.begin():
                    set_tenant_context(session, ctx_a)
                    b_repo = SqlAlchemyWorkspaceRepository(session)
                    assert b_repo.list_for_organization(org_b) == []
            finally:
                session.close()

            # Under B's context: B's workspace visible, A's invisible.
            assert _visible_workspaces(app_mgr, ctx_b) == ["B-ws"]

            # Audit events: each tenant sees only its own (org.created at minimum).
            assert _visible_audit_events(app_mgr, ctx_a) >= 1
            assert _visible_audit_events(app_mgr, ctx_b) >= 1
        finally:
            _cleanup(priv_mgr)
    finally:
        priv_mgr.dispose()
        app_mgr.dispose()
