"""One-time helper: create a dev organization and print its UUID."""

from marketpulse.application.services.audit import AuditService
from marketpulse.application.services.provisioning import TenantProvisioningService
from marketpulse.config import Settings
from marketpulse.core.clock import SystemClock
from marketpulse.domain.tenancy import Role
from marketpulse.infrastructure.db.audit import SqlAlchemyAuditWriter
from marketpulse.infrastructure.db.repositories import (
    SqlAlchemyMembershipRepository,
    SqlAlchemyOrganizationRepository,
    SqlAlchemyUserRepository,
)
from marketpulse.infrastructure.db.session import DatabaseSessionManager


def main() -> None:
    settings = Settings()
    if settings.database_direct_dsn is None:
        raise SystemExit("MP_DATABASE_DIRECT_URL is not set in .env")
    mgr = DatabaseSessionManager.from_dsn(settings.database_direct_dsn)
    session = mgr.session_factory()
    try:
        with session.begin():
            orgs = SqlAlchemyOrganizationRepository(session)
            users = SqlAlchemyUserRepository(session)
            memberships = SqlAlchemyMembershipRepository(session)
            audit = AuditService(SqlAlchemyAuditWriter(session))
            provisioning = TenantProvisioningService(
                orgs, users, memberships, audit, SystemClock()
            )
            org = provisioning.create_organization(
                slug="dev-org",
                display_name="Dev Organization",
                default_market="US",
                timezone="UTC",
                base_currency="USD",
            )
            user = provisioning.create_user(email="dev@local.test", password="dev-password-123")
            provisioning.add_membership(organization_id=org.id, user_id=user.id, role=Role.OWNER)
        print(f"Organization UUID: {org.id}")
    finally:
        mgr.dispose()


if __name__ == "__main__":
    main()