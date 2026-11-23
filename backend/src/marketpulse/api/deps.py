"""FastAPI dependencies: how endpoints receive their collaborators.

Endpoints never build settings, sessions or services themselves. They ask for them
here, and the composition root (``marketpulse.main``) decides what is provided on
``app.state``. Tests swap them freely via ``app.dependency_overrides`` or by
injecting doubles through ``create_app``.

The tenant-scoped dependency chain is, in order:

    get_tenant_context  (resolve the org/user from the request, 401 if absent)
      -> get_db_session (open a tx, SET LOCAL app.tenant_id, yield, commit/rollback)
         -> get_*_service (build repository + service against that session)

Resolution order matters: the tenant context must be known before the session opens,
because ``SET LOCAL`` needs the tenant id, and the session transaction must be open
before ``SET LOCAL`` is issued (ADR-0022). FastAPI resolves dependencies in the order
they appear in the endpoint signature, so endpoints declare ``ctx`` before the
service that consumes the session.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from marketpulse.application.ports.repositories import (
    MembershipRepository,
    OrganizationRepository,
    UserRepository,
    WorkspaceRepository,
)
from marketpulse.application.services.audit import AuditService
from marketpulse.application.services.auth import AuthenticationService
from marketpulse.application.services.organizations import OrganizationService
from marketpulse.application.services.provisioning import TenantProvisioningService
from marketpulse.application.services.readiness import ReadinessService
from marketpulse.application.services.signup import SignupService
from marketpulse.application.services.tenancy import TenantContextService
from marketpulse.application.services.workspaces import WorkspaceService
from marketpulse.config import Settings
from marketpulse.core.clock import Clock
from marketpulse.core.errors import AppError, ErrorCode
from marketpulse.core.ratelimit import FixedWindowRateLimiter
from marketpulse.core.tenancy import TenantContext
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
    SqlAlchemyAuditEventRepository,
    SqlAlchemyMembershipRepository,
    SqlAlchemyOrganizationRepository,
    SqlAlchemyUserRepository,
    SqlAlchemyWorkspaceRepository,
)
from marketpulse.infrastructure.db.session import DatabaseSessionManager, set_tenant_context


# --- Phase 0 dependencies (unchanged) ---
def get_app_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_readiness_service(request: Request) -> ReadinessService:
    return cast(ReadinessService, request.app.state.readiness_service)


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
ReadinessDep = Annotated[ReadinessService, Depends(get_readiness_service)]


# --- Phase 1 dependencies ---
def get_db_manager(request: Request) -> DatabaseSessionManager | None:
    return cast("DatabaseSessionManager | None", getattr(request.app.state, "db_manager", None))


def get_clock(request: Request) -> Clock:
    return cast(Clock, request.app.state.clock)


def get_tenant_context_service(request: Request) -> TenantContextService:
    # The resolver is wired by the composition root (dev header in local/test, auth
    # in Phase 2). It may be None where no tenant source is configured yet; the
    # service fails closed (401) in that case.
    resolver = getattr(request.app.state, "tenant_resolver", None)
    return TenantContextService(resolver)


def get_tenant_context(
    service: Annotated[TenantContextService, Depends(get_tenant_context_service)],
    request: Request,
) -> TenantContext:
    # request.headers is a Starlette Headers (case-insensitive Mapping[str, str]).
    return service.resolve(request.headers)


TenantContextDep = Annotated[TenantContext, Depends(get_tenant_context)]


def get_db_session(
    ctx: TenantContextDep,
    manager: Annotated[DatabaseSessionManager | None, Depends(get_db_manager)],
) -> Iterator[Session]:
    if manager is None:
        # staging/production refuse to start without a database, so this only fires
        # in a misconfigured local environment. Surface it as 503, not a 500.
        raise AppError(
            ErrorCode.SERVICE_UNAVAILABLE,
            "The database is not configured; the service is not ready.",
            status_code=503,
            diagnostic="db_manager is None",
        )
    session = manager.session_factory()
    tx = session.begin()
    try:
        # SET LOCAL must run inside the open transaction; set_tenant_context issues
        # parameterized set_config(..., true) so the tenant id never hits SQL text.
        set_tenant_context(session, ctx)
        yield session
        tx.commit()
    except Exception:
        tx.rollback()
        raise
    finally:
        session.close()


DbSessionDep = Annotated[Session, Depends(get_db_session)]


def get_organization_repository(session: DbSessionDep) -> OrganizationRepository:
    return SqlAlchemyOrganizationRepository(session)


def get_workspace_repository(session: DbSessionDep) -> WorkspaceRepository:
    return SqlAlchemyWorkspaceRepository(session)


def get_audit_writer(session: DbSessionDep) -> SqlAlchemyAuditWriter:
    return SqlAlchemyAuditWriter(session)


def get_audit_service(
    writer: Annotated[SqlAlchemyAuditWriter, Depends(get_audit_writer)],
) -> AuditService:
    return AuditService(writer)


def get_organization_service(
    orgs: Annotated[OrganizationRepository, Depends(get_organization_repository)],
) -> OrganizationService:
    return OrganizationService(orgs)


def get_workspace_service(
    workspaces: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
    audit: Annotated[AuditService, Depends(get_audit_service)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> WorkspaceService:
    return WorkspaceService(workspaces, audit, clock)


def get_audit_event_repository(session: DbSessionDep) -> SqlAlchemyAuditEventRepository:
    return SqlAlchemyAuditEventRepository(session)


OrganizationServiceDep = Annotated[OrganizationService, Depends(get_organization_service)]
WorkspaceServiceDep = Annotated[WorkspaceService, Depends(get_workspace_service)]
AuditEventRepositoryDep = Annotated[
    SqlAlchemyAuditEventRepository, Depends(get_audit_event_repository)
]
ClockDep = Annotated[Clock, Depends(get_clock)]


# --- Phase 2 dependencies (authentication) ---
def get_priv_db_manager(request: Request) -> DatabaseSessionManager | None:
    """The PRIVILEGED manager (direct URL, owner role): migrations/provisioning/signup."""
    state = getattr(request.app.state, "priv_db_manager", None)
    return cast("DatabaseSessionManager | None", state)


def get_priv_session(
    manager: Annotated[DatabaseSessionManager | None, Depends(get_priv_db_manager)],
) -> Iterator[Session]:
    """A RAW privileged session (no transaction, no tenant GUC).

    The handler opens and commits its own transaction with ``with session.begin():`` —
    register must COMMIT the account before the session row is created, because a
    foreign key cannot see an uncommitted row from another transaction.
    """
    if manager is None:
        raise AppError(
            ErrorCode.SERVICE_UNAVAILABLE,
            "Signup is not available: the privileged database connection is not configured.",
            status_code=503,
            diagnostic="priv_db_manager is None",
        )
    session = manager.session_factory()
    try:
        yield session
    finally:
        session.close()


def get_plain_session(
    manager: Annotated[DatabaseSessionManager | None, Depends(get_db_manager)],
) -> Iterator[Session]:
    """A RAW application-role session with NO tenant context (global tables only).

    Used by login/logout/switch: ``auth_sessions`` and ``users`` are not tenant-
    scoped, so setting ``app.tenant_id`` would be meaningless here. Per-user /
    per-tenant scoping is applied inside the adapters when a read needs it.
    """
    if manager is None:
        raise AppError(
            ErrorCode.SERVICE_UNAVAILABLE,
            "The database is not configured; the service is not ready.",
            status_code=503,
            diagnostic="db_manager is None",
        )
    session = manager.session_factory()
    try:
        yield session
    finally:
        session.close()


def get_rate_limiter(request: Request) -> FixedWindowRateLimiter:
    return cast(FixedWindowRateLimiter, request.app.state.auth_rate_limiter)


def build_auth_service(session: Session, settings: Settings, clock: Clock) -> AuthenticationService:
    """Compose the auth use case on ONE plain session (handler-owned transaction)."""
    return AuthenticationService(
        credentials=SqlAlchemyCredentialReader(session),
        sessions=SqlAlchemySessionStore(session),
        memberships=SqlAlchemyMembershipByUserReader(session),
        organizations=SqlAlchemyOrganizationRepository(session),
        users=SqlAlchemyUserAccountReader(session),
        tenant_scope=SqlAlchemyTenantScope(session),
        hasher=Argon2PasswordHasher(),
        tokens=SecretsTokenGenerator(),
        clock=clock,
        session_lifetime=timedelta(hours=settings.session_lifetime_hours),
    )


def build_signup_service(session: Session, clock: Clock) -> SignupService:
    """Compose signup on ONE privileged session (handler-owned transaction)."""
    audit = AuditService(SqlAlchemyAuditWriter(session))
    orgs = SqlAlchemyOrganizationRepository(session)
    provisioning = TenantProvisioningService(
        orgs,
        SqlAlchemyUserRepository(session),
        SqlAlchemyMembershipRepository(session),
        audit,
        clock,
    )
    workspaces = WorkspaceService(
        SqlAlchemyWorkspaceRepository(session), AuditService(SqlAlchemyAuditWriter(session)), clock
    )
    return SignupService(provisioning, workspaces, orgs)


def get_user_repository(session: DbSessionDep) -> UserRepository:
    return SqlAlchemyUserRepository(session)


def get_membership_repository(session: DbSessionDep) -> MembershipRepository:
    return SqlAlchemyMembershipRepository(session)


PrivSessionDep = Annotated[Session, Depends(get_priv_session)]
PlainSessionDep = Annotated[Session, Depends(get_plain_session)]
RateLimiterDep = Annotated[FixedWindowRateLimiter, Depends(get_rate_limiter)]
UserRepositoryDep = Annotated[UserRepository, Depends(get_user_repository)]
MembershipRepositoryDep = Annotated[MembershipRepository, Depends(get_membership_repository)]
OrganizationRepositoryDep = Annotated[OrganizationRepository, Depends(get_organization_repository)]
