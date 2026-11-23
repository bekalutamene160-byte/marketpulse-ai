"""Domain entities for the tenant foundation (blueprint 7.4).

Pure frozen dataclasses with no framework imports. The persistence layer
(``infrastructure/db``) maps these to and from SQLAlchemy ORM rows; use cases and
tests operate only on these types, so the business logic is testable in
milliseconds without a database and without importing SQLAlchemy.

Notable choice: the ``User`` entity deliberately has NO ``password_hash`` field.
A domain object never carries a credential. Hashing is an infrastructure concern
(``core.security``) and the hash never crosses the persistence boundary into a
use case. Phase 2's login flow will read the hash through a dedicated credential
check, not through a domain ``User``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from marketpulse.domain.tenancy import MembershipStatus, Role, UserStatus


@dataclass(frozen=True, slots=True)
class Organization:
    """A tenant root. All tenant-scoped rows carry this id as ``organization_id``."""

    id: uuid.UUID
    slug: str
    display_name: str
    default_market: str | None
    timezone: str
    base_currency: str
    is_demo: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Workspace:
    """A workspace within an organization (blueprint 7.4: demo/read-only flags)."""

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    is_read_only: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class User:
    """An identity. Global, not tenant-scoped: one user may belong to many orgs."""

    id: uuid.UUID
    email: str
    status: UserStatus
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Membership:
    """The user-to-organization link carrying a role and lifecycle state."""

    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    role: Role
    status: MembershipStatus
    created_at: datetime


@dataclass(frozen=True, slots=True)
class MemberSummary:
    """A membership row joined with the member's email (the org member list view).

    This is a READ VIEW, deliberately small: it exposes exactly what a member list
    needs (who, what role, since when) and nothing else. It exists so the RLS-secured
    ``memberships -> users`` join can be returned without ever materializing a global
    user list (Phase 1 invariant: ``users`` is never enumerated cross-tenant; only
    members of YOUR org are visible, and only through your own tenant's membership
    rows).
    """

    membership_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    role: Role
    status: MembershipStatus
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AuthSession:
    """A server-side login session (blueprint 15.1).

    The browser holds an opaque random token in an HttpOnly cookie; only the token's
    SHA-256 digest is stored here, so a database leak cannot be replayed as a login.
    ``csrf_token_hash`` binds the CSRF token the SPA echoes in ``X-CSRF-Token`` to
    this exact session. ``organization_id`` is the user's ACTIVE organization (the
    workspace selector); it is nullable because a user may temporarily have no
    membership, and the FK cascades so deleting an organization ends its sessions.
    A session belongs to a user, not to a tenant: like ``users``, it is global and
    carries no row-level security.
    """

    id: uuid.UUID
    user_id: uuid.UUID
    token_hash: str
    csrf_token_hash: str
    organization_id: uuid.UUID | None
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """An immutable record of a security-relevant action (blueprint 7.4, 16.3).

    ``metadata`` holds only safe, non-secret values (slugs, role names, counts).
    Credentials, full payloads, and PII never go here. ``request_id`` ties the
    event to the structured log line and trace for incident investigation.
    """

    id: uuid.UUID
    organization_id: uuid.UUID
    actor_user_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: uuid.UUID
    occurred_at: datetime
    request_id: str
    metadata: dict[str, Any]
