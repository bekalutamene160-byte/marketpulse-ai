"""Ports for authentication: hashing, tokens, credentials and session storage.

Phase 2 splits authentication into ports so the use cases in
``application/services/auth.py`` never import Argon2, ``secrets``, or SQLAlchemy
(blueprint 5.4): a use case is testable with fakes in milliseconds, and each real
implementation lives in ``infrastructure``.

Everything here is deliberately narrow:

- ``PasswordHasher`` wraps only the three Argon2id operations the auth flow needs.
- ``TokenGenerator`` produces opaque, high-entropy strings; only their SHA-256
  digests are ever persisted (``core.cookies.hash_token``).
- ``CredentialReader`` returns the ``(user, password_hash)`` pair for an email. The
  hash must not travel on the domain ``User`` (Phase 1 invariant), so the pair is
  returned as a tuple and the hash never leaves the authentication path.
- ``SessionStore`` owns the ``auth_sessions`` lifecycle: create, find by token hash
  (expiry-checked), set the active organization, touch ``last_seen_at``, delete,
  and opportunistic garbage collection of expired rows for a user.
- ``UserAccountReader`` answers "does this user id exist and is it active?" for the
  session resolver.
- ``TenantScopeSetter`` establishes the tenant GUC (``app.tenant_id``, ADR-0022) on a
  plain (tenant-less) session so an organization row can be read under RLS after the
  membership check. Implementations issue parameterized ``set_config(..., true)`` —
  never interpolated SQL. (The per-user ``app.user_id`` scope is handled INSIDE the
  ``MembershipReader`` adapter, which is the only reader that needs it.)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol

from marketpulse.core.tenancy import TenantContext
from marketpulse.domain.entities import AuthSession, Membership, User


class PasswordHasher(Protocol):
    def hash(self, plaintext: str) -> str: ...
    def verify(self, hashed: str, plaintext: str) -> bool: ...
    def needs_rehash(self, hashed: str) -> bool: ...


class TokenGenerator(Protocol):
    def new_token(self) -> str: ...


class CredentialReader(Protocol):
    def get_credentials_by_email(self, email: str) -> tuple[User, str] | None: ...


class SessionStore(Protocol):
    def create(self, session: AuthSession) -> None: ...
    def find_active_by_token_hash(self, token_hash: str, now: datetime) -> AuthSession | None: ...
    def delete(self, session_id: uuid.UUID) -> None: ...
    def set_organization(self, session_id: uuid.UUID, org_id: uuid.UUID) -> None: ...
    def touch(self, session_id: uuid.UUID, now: datetime) -> None: ...
    def delete_expired_for_user(self, user_id: uuid.UUID, now: datetime) -> None: ...


class UserAccountReader(Protocol):
    def get_active_user(self, user_id: uuid.UUID) -> User | None: ...


class TenantScopeSetter(Protocol):
    def set_tenant(self, organization_id: uuid.UUID) -> None: ...


class MembershipReader(Protocol):
    """Reads memberships for ONE user via the per-user RLS policy (ADR-0026).

    The adapter establishes the ``app.user_id`` security context itself, so a plain
    (tenant-less) session can read exactly this user's membership rows and nothing
    else. Ordered oldest-first so ``login`` picks a deterministic default
    organization.
    """

    def list_for_user(self, user_id: uuid.UUID) -> list[Membership]: ...


def session_context_for(session: AuthSession) -> TenantContext | None:
    """The tenant context a stored session implies, or None when it cannot act.

    A session without an active organization (its org was deleted — the FK cascades
    the session row too — or the user has no membership) must NOT yield a tenant
    context: tenant-scoped endpoints fail closed with 401 until the user logs in
    again and a default organization is chosen.
    """
    if session.organization_id is None:
        return None
    return TenantContext(organization_id=session.organization_id, user_id=session.user_id)


__all__ = [
    "CredentialReader",
    "MembershipReader",
    "PasswordHasher",
    "SessionStore",
    "TenantScopeSetter",
    "TokenGenerator",
    "UserAccountReader",
    "session_context_for",
]
