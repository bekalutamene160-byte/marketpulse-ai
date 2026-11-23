"""SQLAlchemy adapters for the authentication ports (Phase 2, ADR-0025).

Every adapter here runs inside the CALLER's session/transaction: the plain
application-role session opened by ``api.deps.get_plain_db_session`` (login, logout,
switch, session store) or the privileged session (signup). None of them opens a
transaction of its own.

Security notes kept in one place:

- Tokens are persisted ONLY as SHA-256 digests (``core.cookies.hash_token``); the
  plaintext exists for the instant between generation and Set-Cookie.
- ``SqlAlchemyMembershipByUserReader`` sets the transaction-local ``app.user_id`` GUC
  (parameterized ``set_config(..., true)``, never interpolated) before reading, so
  the per-user RLS policy (migration 0002, ADR-0026) reveals exactly that user's
  membership rows on a plain, tenant-less session.
- ``SqlAlchemyTenantScope`` sets ``app.tenant_id`` the same way, letting a plain
  session read one organization row under RLS after a membership check.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime

from sqlalchemy import delete, select, text, update
from sqlalchemy.orm import Session

from marketpulse.application.ports.auth import (
    MembershipReader,
)
from marketpulse.core.security import hash_password, needs_rehash, verify_password
from marketpulse.domain.entities import AuthSession, Membership, User
from marketpulse.domain.tenancy import UserStatus
from marketpulse.infrastructure.db.models import (
    AuthSessionORM,
    MembershipORM,
    UserORM,
)
from marketpulse.infrastructure.db.repositories import _to_membership, _to_user


class Argon2PasswordHasher:
    """Adapter over ``core.security`` (the same pinned Argon2id parameters)."""

    def hash(self, plaintext: str) -> str:
        return hash_password(plaintext)

    def verify(self, hashed: str, plaintext: str) -> bool:
        return verify_password(hashed, plaintext)

    def needs_rehash(self, hashed: str) -> bool:
        return needs_rehash(hashed)


class SecretsTokenGenerator:
    """`secrets.token_urlsafe(32)`: ~192 bits of entropy, URL-safe, no padding."""

    def new_token(self) -> str:
        return secrets.token_urlsafe(32)


class SqlAlchemyCredentialReader:
    """Reads the ``(user, password_hash)`` pair for one email from the global table."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_credentials_by_email(self, email: str) -> tuple[User, str] | None:
        row = self._session.execute(
            select(UserORM).where(UserORM.email == email.lower().strip())
        ).scalar_one_or_none()
        if row is None:
            return None
        # The hash NEVER joins the domain User; it travels beside it, once, to the
        # Argon2id verifier only.
        return _to_user(row), row.password_hash


class SqlAlchemyUserAccountReader:
    """Answers "does this user id exist and is it active?" for session resolution."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_active_user(self, user_id: uuid.UUID) -> User | None:
        row = self._session.get(UserORM, user_id)
        if row is None or row.status != UserStatus.ACTIVE.value:
            return None
        return _to_user(row)


class SqlAlchemySessionStore:
    """Lifecycle of ``auth_sessions`` rows, mapped to/from the domain entity."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, session_entity: AuthSession) -> None:
        self._session.add(
            AuthSessionORM(
                id=session_entity.id,
                user_id=session_entity.user_id,
                token_hash=session_entity.token_hash,
                csrf_token_hash=session_entity.csrf_token_hash,
                organization_id=session_entity.organization_id,
                created_at=session_entity.created_at,
                last_seen_at=session_entity.last_seen_at,
                expires_at=session_entity.expires_at,
            )
        )

    def find_active_by_token_hash(self, token_hash: str, now: datetime) -> AuthSession | None:
        row = self._session.execute(
            select(AuthSessionORM).where(
                AuthSessionORM.token_hash == token_hash,
                AuthSessionORM.expires_at > now,
            )
        ).scalar_one_or_none()
        return self._to_entity(row) if row is not None else None

    def delete(self, session_id: uuid.UUID) -> None:
        self._session.execute(delete(AuthSessionORM).where(AuthSessionORM.id == session_id))

    def set_organization(self, session_id: uuid.UUID, org_id: uuid.UUID) -> None:
        self._session.execute(
            update(AuthSessionORM)
            .where(AuthSessionORM.id == session_id)
            .values(organization_id=org_id)
        )

    def touch(self, session_id: uuid.UUID, now: datetime) -> None:
        self._session.execute(
            update(AuthSessionORM).where(AuthSessionORM.id == session_id).values(last_seen_at=now)
        )

    def delete_expired_for_user(self, user_id: uuid.UUID, now: datetime) -> None:
        self._session.execute(
            delete(AuthSessionORM).where(
                AuthSessionORM.user_id == user_id,
                AuthSessionORM.expires_at <= now,
            )
        )

    @staticmethod
    def _to_entity(row: AuthSessionORM) -> AuthSession:
        return AuthSession(
            id=row.id,
            user_id=row.user_id,
            token_hash=row.token_hash,
            csrf_token_hash=row.csrf_token_hash,
            organization_id=row.organization_id,
            created_at=row.created_at,
            last_seen_at=row.last_seen_at,
            expires_at=row.expires_at,
        )


class SqlAlchemyTenantScope:
    """Sets the transaction-local tenant GUC on a plain session (ADR-0022)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def set_tenant(self, organization_id: uuid.UUID) -> None:
        self._session.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"),
            {"tid": str(organization_id)},
        )


class SqlAlchemyMembershipByUserReader(MembershipReader):
    """Lists ONE user's memberships under the per-user policy (ADR-0026).

    Establishes ``app.user_id`` first: on a plain session with NO tenant GUC, the
    0001 tenant policy matches nothing (default-deny) and this user policy is the
    only way the application role may read membership rows — exactly its own.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_user(self, user_id: uuid.UUID) -> list[Membership]:
        self._session.execute(
            text("SELECT set_config('app.user_id', :uid, true)"),
            {"uid": str(user_id)},
        )
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
