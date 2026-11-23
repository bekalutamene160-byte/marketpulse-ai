"""Integration test: real authentication against live Neon (Phase 2 gate).

Proves the whole session path on a real PostgreSQL with the application role:
signup on the privileged connection, session creation under the app role, the
cookie resolver, tenant-scoped reads, the per-user RLS policies (membership list
across orgs + organization visibility for the selector), organization switching,
logout revocation, and the default-deny behaviour when no GUC is set.

    MP_DATABASE_URL=... MP_DATABASE_DIRECT_URL=... uv run pytest -m integration \
        tests/integration/test_auth_live.py
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from marketpulse.application.services.audit import AuditService
from marketpulse.application.services.auth import AuthenticationService
from marketpulse.application.services.provisioning import TenantProvisioningService
from marketpulse.application.services.signup import SignupService
from marketpulse.application.services.workspaces import WorkspaceService
from marketpulse.core.clock import SystemClock
from marketpulse.core.cookies import SESSION_COOKIE
from marketpulse.domain.entities import AuthSession
from marketpulse.domain.tenancy import Role
from marketpulse.infrastructure.db.audit import SqlAlchemyAuditWriter
from marketpulse.infrastructure.db.auth import (
    Argon2PasswordHasher,
    SecretsTokenGenerator,
    SqlAlchemyCredentialReader,
    SqlAlchemyMembershipByUserReader,
    SqlAlchemySessionStore,
    SqlAlchemyTenantScope,
    SqlAlchemyUserAccountReader,
)
from marketpulse.infrastructure.db.repositories import (
    SqlAlchemyMembershipRepository,
    SqlAlchemyOrganizationRepository,
    SqlAlchemyUserRepository,
    SqlAlchemyWorkspaceRepository,
)
from marketpulse.infrastructure.db.session import DatabaseSessionManager, set_tenant_context
from marketpulse.infrastructure.tenancy.session_resolver import SessionTenantContextResolver

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-battery"


def _auth_service(session) -> AuthenticationService:
    """The same composition the API dependency uses, on the given plain session."""
    return AuthenticationService(
        credentials=SqlAlchemyCredentialReader(session),
        sessions=SqlAlchemySessionStore(session),
        memberships=SqlAlchemyMembershipByUserReader(session),
        organizations=SqlAlchemyOrganizationRepository(session),
        users=SqlAlchemyUserAccountReader(session),
        tenant_scope=SqlAlchemyTenantScope(session),
        hasher=Argon2PasswordHasher(),
        tokens=SecretsTokenGenerator(),
        clock=SystemClock(),
    )


def _signup(priv_mgr: DatabaseSessionManager, email: str, slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    """Create an org + owner user + General workspace on the privileged connection."""
    session = priv_mgr.session_factory()
    try:
        with session.begin():
            clock = SystemClock()
            orgs = SqlAlchemyOrganizationRepository(session)
            provisioning = TenantProvisioningService(
                orgs,
                SqlAlchemyUserRepository(session),
                SqlAlchemyMembershipRepository(session),
                AuditService(SqlAlchemyAuditWriter(session)),
                clock,
            )
            workspaces = WorkspaceService(
                SqlAlchemyWorkspaceRepository(session),
                AuditService(SqlAlchemyAuditWriter(session)),
                clock,
            )
            signup = SignupService(provisioning, workspaces, orgs)
            org, user = signup.register(email=email, password=PASSWORD, organization_name=slug)
            return org.id, user.id
    finally:
        session.close()


def _login(app_mgr: DatabaseSessionManager, email: str) -> tuple[AuthSession, str, str]:
    """Login under the app role; returns the row and the RAW cookie material."""
    session = app_mgr.session_factory()
    try:
        with session.begin():
            outcome = _auth_service(session).login(email=email, password=PASSWORD)
            return outcome.tokens.session, outcome.tokens.session_token, outcome.tokens.csrf_token
    finally:
        session.close()


def _provision_second_org(priv_mgr: DatabaseSessionManager, user_id: uuid.UUID) -> uuid.UUID:
    session = priv_mgr.session_factory()
    try:
        with session.begin():
            provisioning = TenantProvisioningService(
                SqlAlchemyOrganizationRepository(session),
                SqlAlchemyUserRepository(session),
                SqlAlchemyMembershipRepository(session),
                AuditService(SqlAlchemyAuditWriter(session)),
                SystemClock(),
            )
            org = provisioning.create_organization(
                slug=f"live-auth-b-{uuid.uuid4().hex[:8]}",
                display_name="Live B",
                default_market=None,
                timezone="UTC",
                base_currency="USD",
            )
            provisioning.add_membership(organization_id=org.id, user_id=user_id, role=Role.MEMBER)
            return org.id
    finally:
        session.close()


def _cleanup(priv_mgr: DatabaseSessionManager, orgs: list[uuid.UUID], user_id: uuid.UUID) -> None:
    session = priv_mgr.session_factory()
    try:
        with session.begin():
            if orgs:
                # Deleting the orgs cascades memberships, workspaces, audit events
                # and (via the session table's org FK) the auth sessions.
                session.execute(
                    text("DELETE FROM organizations WHERE id = ANY(:ids)"), {"ids": orgs}
                )
            session.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
    finally:
        session.close()


def test_authentication_session_isolation_and_switch(
    migrated_schema: str, app_role_dsn: str
) -> None:
    priv_mgr = DatabaseSessionManager.from_dsn(migrated_schema, pool_size=2, max_overflow=0)
    app_mgr = DatabaseSessionManager.from_dsn(app_role_dsn, pool_size=2, max_overflow=0)
    email = f"live-auth-{uuid.uuid4().hex[:10]}@iso.test"
    org_a: uuid.UUID | None = None
    org_b: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    try:
        # --- 1) signup on the privileged connection ---
        org_a, user_id = _signup(priv_mgr, email, f"Live A {email[:12]}")

        # --- 2) login under the app role: a session row exists ---
        session_row, session_token, csrf_token = _login(app_mgr, email)
        assert session_row.user_id == user_id
        assert session_row.organization_id == org_a

        # --- 3) the session resolver turns the cookie into a tenant context ---
        resolver = SessionTenantContextResolver(app_mgr.session_factory, SystemClock())
        ctx = resolver.resolve({"cookie": f"{SESSION_COOKIE}={session_token}"})
        assert ctx is not None
        assert ctx.organization_id == org_a
        assert ctx.user_id == user_id

        # --- 4) tenant-scoped read under the app role works with that context ---
        session = app_mgr.session_factory()
        try:
            with session.begin():
                set_tenant_context(session, ctx)
                assert SqlAlchemyOrganizationRepository(session).get(org_a) is not None
                rows = SqlAlchemyMembershipRepository(session).list_for_user(user_id)
                assert [m.organization_id for m in rows] == [org_a]
        finally:
            session.close()

        # --- 5) a second org + membership: the selector view grows correctly ---
        org_b = _provision_second_org(priv_mgr, user_id)
        session = app_mgr.session_factory()
        try:
            with session.begin():
                set_tenant_context(session, ctx)
                rows = SqlAlchemyMembershipRepository(session).list_for_user(user_id)
                assert {m.organization_id for m in rows} == {org_a, org_b}
                # The organizations_user_access policy: BOTH org rows are readable.
                orgs = SqlAlchemyOrganizationRepository(session).list_by_ids([org_a, org_b])
                assert {o.id for o in orgs} == {org_a, org_b}
        finally:
            session.close()

        # --- 6) default-deny: with NO GUC the app role sees nothing ---
        session = app_mgr.session_factory()
        try:
            with session.begin():
                assert session.execute(text("SELECT count(*) FROM memberships")).scalar_one() == 0
                assert session.execute(text("SELECT count(*) FROM organizations")).scalar_one() == 0
        finally:
            session.close()

        # --- 7) switching requires membership; logout revokes ---
        with app_mgr.session_factory() as plain, plain.begin():
            auth = _auth_service(plain)
            switched = auth.switch_organization(
                session_token=session_token,
                csrf_token=csrf_token,
                organization_id=org_b,
            )
            assert switched.id == org_b
            with pytest.raises(Exception):  # noqa: B017 - non-member org must be denied
                auth.switch_organization(
                    session_token=session_token,
                    csrf_token=csrf_token,
                    organization_id=uuid.uuid4(),
                )

        with app_mgr.session_factory() as plain, plain.begin():
            _auth_service(plain).logout(session_token=session_token, csrf_token=csrf_token)
        assert resolver.resolve({"cookie": f"{SESSION_COOKIE}={session_token}"}) is None

        # --- 8) a stranger's cookie never resolves ---
        assert resolver.resolve({"cookie": f"{SESSION_COOKIE}=garbage-value"}) is None
    finally:
        tracked = [o for o in (org_a, org_b) if o is not None]
        if user_id is not None:
            _cleanup(priv_mgr, tracked, user_id)
        priv_mgr.dispose()
        app_mgr.dispose()
