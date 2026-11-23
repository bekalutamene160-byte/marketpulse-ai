"""Use case: self-service signup — creates a user's first organization (FR-001).

Why a separate service: signup is the ONE application path that must create an
organization, and organizations can only be created by the PRIVILEGED provisioning
path (row-level security makes it impossible for the application role to insert an
organization whose id it cannot know in advance — see ``TenantProvisioningService``
and ADR-0023). This service therefore runs on a privileged session owned by the
request dependency, and reuses the existing provisioning + workspace services rather
than duplicating their rules (blueprint 24.6: preserve working code).

What one signup produces, in one transaction:

1. An organization with a UNIQUE, URL-safe slug derived from the requested name
   (``"Acme Ltd"`` -> ``acme-ltd``; conflicts get ``-2``, ``-3``, ... suffixes).
2. The user (email lowercased; Argon2id hash via the provisioning path).
3. An owner membership for the creator.
4. A ``General`` workspace so the shell shows real data on first login.
5. The normal tenant audit rows (organization.created, membership.added,
   workspace.created), written by the reused services themselves.

Validation happens here with explicit, user-safe messages; the provisioning service
adds the uniqueness checks (duplicate email / slug -> 409 CONFLICT) that also protect
against races between check and insert.
"""

from __future__ import annotations

import re

from marketpulse.application.ports.repositories import OrganizationRepository
from marketpulse.application.services.provisioning import TenantProvisioningService
from marketpulse.application.services.workspaces import WorkspaceService
from marketpulse.core.errors import AppError, ErrorCode
from marketpulse.core.tenancy import TenantContext
from marketpulse.domain.entities import Organization, User
from marketpulse.domain.tenancy import Role

#: Slug charset. Derived slugs are safe unquoted identifiers in URLs.
_SLUG_SAFE = re.compile(r"[^a-z0-9]+")
_MAX_SLUG = 63  # matches organizations.slug VARCHAR(63)
_MAX_NAME = 200  # matches organizations.display_name VARCHAR(200)
_MIN_PASSWORD = 12
_MAX_PASSWORD = 128
#: The default workspace every new organization starts with.
DEFAULT_WORKSPACE_NAME = "General"

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class SignupService:
    def __init__(
        self,
        provisioning: TenantProvisioningService,
        workspaces: WorkspaceService,
        orgs: OrganizationRepository,
    ) -> None:
        self._provisioning = provisioning
        self._workspaces = workspaces
        self._orgs = orgs

    def register(
        self, *, email: str, password: str, organization_name: str
    ) -> tuple[Organization, User]:
        email = email.strip().lower()
        organization_name = organization_name.strip()
        if not _EMAIL.match(email):
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "Enter a valid email address.",
                status_code=422,
                diagnostic=f"email format rejected for {email}",
            )
        if not (_MIN_PASSWORD <= len(password) <= _MAX_PASSWORD):
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                f"Password must be {_MIN_PASSWORD} to {_MAX_PASSWORD} characters.",
                status_code=422,
                diagnostic=f"password length={len(password)}",
            )
        if not organization_name or len(organization_name) > _MAX_NAME:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                f"Organization name must be 1 to {_MAX_NAME} characters.",
                status_code=422,
                diagnostic=f"organization_name length={len(organization_name)}",
            )

        slug = self._unique_slug(organization_name)
        org = self._provisioning.create_organization(
            slug=slug,
            display_name=organization_name,
            default_market=None,
            timezone="UTC",
            base_currency="USD",
        )
        user = self._provisioning.create_user(email=email, password=password)
        self._provisioning.add_membership(organization_id=org.id, user_id=user.id, role=Role.OWNER)
        self._workspaces.create(
            ctx=TenantContext(organization_id=org.id), name=DEFAULT_WORKSPACE_NAME
        )
        return org, user

    def _unique_slug(self, organization_name: str) -> str:
        """Derive a URL-safe slug; on collision append -2, -3, ... (bounded).

        The pre-check uses the same repository the provisioning service will use in
        the same transaction, so the loop is deterministic. A racing duplicate still
        surfaces as the provisioning service's 409 CONFLICT rather than a surprise.
        """
        base = _SLUG_SAFE.sub("-", organization_name.lower()).strip("-")
        base = base[:_MAX_SLUG].strip("-") or "org"
        candidate = base
        for suffix in range(2, 100):
            if self._orgs.get_by_slug(candidate) is None:
                return candidate
            tail = f"-{suffix}"
            candidate = f"{base[: _MAX_SLUG - len(tail)]}{tail}"
        raise AppError(
            ErrorCode.CONFLICT,
            "Could not derive a unique organization address. Try a different name.",
            status_code=409,
            diagnostic=f"slug derivation exhausted for base={base}",
        )
