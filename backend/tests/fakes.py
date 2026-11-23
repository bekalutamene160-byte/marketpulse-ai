"""Test doubles.

Phase 0 doubles for the ``HealthProbe`` port are kept. Phase 1 adds in-memory doubles
for the repository and audit ports, plus a fake clock and tenant resolver, so use
cases and the API layer are testable in milliseconds with no database. The fakes
record their calls so tests can assert behaviour, not just state.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from marketpulse.application.ports.audit import AuditEventWriter
from marketpulse.application.ports.health import ProbeResult
from marketpulse.application.ports.tenancy import TenantContextResolver
from marketpulse.core.clock import Clock
from marketpulse.core.tenancy import TenantContext
from marketpulse.domain.audit import AuditAction
from marketpulse.domain.entities import (
    AuditEvent,
    Membership,
    Organization,
    User,
    Workspace,
)
from marketpulse.domain.tenancy import MembershipStatus, Role, UserStatus


# --- Phase 0: HealthProbe doubles ---
class FakeProbe:
    """Returns a fixed result."""

    def __init__(self, name: str, result: ProbeResult, *, required: bool = True) -> None:
        self.name = name
        self.required = required
        self._result = result

    async def check(self) -> ProbeResult:
        return self._result


class RaisingProbe:
    """A buggy probe: raises instead of returning a result."""

    def __init__(self, name: str = "buggy", *, required: bool = True) -> None:
        self.name = name
        self.required = required

    async def check(self) -> ProbeResult:
        raise RuntimeError("secret-internal-detail")


class SlowProbe:
    """Never finishes within a sensible time."""

    def __init__(self, name: str = "slow", *, required: bool = True) -> None:
        self.name = name
        self.required = required

    async def check(self) -> ProbeResult:
        await asyncio.sleep(30)
        return ProbeResult("ok")


AnyProbe = FakeProbe | RaisingProbe | SlowProbe


# --- Phase 1 doubles ---
class FakeClock(Clock):
    def __init__(self, fixed_now: datetime) -> None:
        self._fixed = fixed_now

    def utcnow(self) -> datetime:
        return self._fixed


class FakeTenantContextResolver(TenantContextResolver):
    """Always returns the context it was built with (or None to simulate no auth)."""

    def __init__(self, ctx: TenantContext | None) -> None:
        self._ctx = ctx
        self.calls: list[Mapping[str, str]] = []

    def resolve(self, headers: Mapping[str, str]) -> TenantContext | None:
        self.calls.append(headers)
        return self._ctx


class RecordingAuditWriter(AuditEventWriter):
    """Records every write call; never persists."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def write(
        self,
        *,
        ctx: TenantContext,
        action: AuditAction,
        entity_type: str,
        entity_id: uuid.UUID,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.events.append(
            {
                "ctx": ctx,
                "action": action,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "metadata": metadata or {},
            }
        )


class FakeOrganizationRepository:
    def __init__(self) -> None:
        self._by_id: dict[uuid.UUID, Organization] = {}
        self._by_slug: dict[str, Organization] = {}

    def add(self, org: Organization) -> None:
        self._by_id[org.id] = org
        self._by_slug[org.slug] = org

    def get(self, org_id: uuid.UUID) -> Organization | None:
        return self._by_id.get(org_id)

    def get_by_slug(self, slug: str) -> Organization | None:
        return self._by_slug.get(slug)


class FakeWorkspaceRepository:
    def __init__(self) -> None:
        self._rows: list[Workspace] = []

    def add(self, workspace: Workspace) -> None:
        self._rows.append(workspace)

    def get(self, workspace_id: uuid.UUID, org_id: uuid.UUID) -> Workspace | None:
        for w in self._rows:
            if w.id == workspace_id and w.organization_id == org_id:
                return w
        return None

    def list_for_organization(self, org_id: uuid.UUID) -> list[Workspace]:
        return [w for w in self._rows if w.organization_id == org_id]


class FakeUserRepository:
    def __init__(self) -> None:
        self._by_id: dict[uuid.UUID, User] = {}
        self._by_email: dict[str, User] = {}
        self.hashes: dict[uuid.UUID, str] = {}

    def add(self, user: User, password_hash: str) -> None:
        self._by_id[user.id] = user
        self._by_email[user.email] = user
        self.hashes[user.id] = password_hash

    def get(self, user_id: uuid.UUID) -> User | None:
        return self._by_id.get(user_id)

    def get_by_email(self, email: str) -> User | None:
        return self._by_email.get(email.lower())


class FakeMembershipRepository:
    def __init__(self) -> None:
        self._rows: list[Membership] = []

    def add(self, membership: Membership) -> None:
        self._rows.append(membership)

    def list_for_organization(self, org_id: uuid.UUID) -> list[Membership]:
        return [m for m in self._rows if m.organization_id == org_id]


class FakeAuditEventRepository:
    def __init__(self, rows: list[AuditEvent] | None = None) -> None:
        self._rows = list(rows or [])
        self.listed: list[tuple[uuid.UUID, int]] = []

    def list_for_organization(self, org_id: uuid.UUID, *, limit: int = 100) -> list[AuditEvent]:
        self.listed.append((org_id, limit))
        return [e for e in self._rows if e.organization_id == org_id][:limit]


def make_user(
    *,
    id: uuid.UUID | None = None,
    email: str = "owner@example.com",
    status: UserStatus = UserStatus.ACTIVE,
    created_at: datetime | None = None,
) -> User:
    return User(
        id=id or uuid.uuid4(),
        email=email,
        status=status,
        created_at=created_at or datetime(2026, 1, 1, 0, 0, 0),
        updated_at=created_at or datetime(2026, 1, 1, 0, 0, 0),
    )


def make_organization(
    *,
    id: uuid.UUID | None = None,
    slug: str = "acme",
    display_name: str = "Acme",
    is_demo: bool = False,
    created_at: datetime | None = None,
) -> Organization:
    return Organization(
        id=id or uuid.uuid4(),
        slug=slug,
        display_name=display_name,
        default_market="US",
        timezone="UTC",
        base_currency="USD",
        is_demo=is_demo,
        created_at=created_at or datetime(2026, 1, 1, 0, 0, 0),
        updated_at=created_at or datetime(2026, 1, 1, 0, 0, 0),
    )


def make_membership(
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    role: Role = Role.OWNER,
    status: MembershipStatus = MembershipStatus.ACTIVE,
) -> Membership:
    return Membership(
        id=uuid.uuid4(),
        organization_id=organization_id,
        user_id=user_id,
        role=role,
        status=status,
        created_at=datetime(2026, 1, 1, 0, 0, 0),
    )


# --- Phase 2 doubles ---
from marketpulse.application.ports.auth import (  # noqa: E402
    CredentialReader,
    MembershipReader,
    PasswordHasher,
    SessionStore,
    TenantScopeSetter,
    TokenGenerator,
    UserAccountReader,
)
from marketpulse.domain.entities import AuthSession, MemberSummary  # noqa: E402


class FakePasswordHasher(PasswordHasher):
    """Deterministic, instant hashing for tests: prefix + reversal."""

    def __init__(self) -> None:
        self.rehash_needed: set[str] = set()

    def hash(self, plaintext: str) -> str:
        return f"fakehash::{plaintext[::-1]}"

    def verify(self, hashed: str, plaintext: str) -> bool:
        return hashed == f"fakehash::{plaintext[::-1]}"

    def needs_rehash(self, hashed: str) -> bool:
        return hashed in self.rehash_needed


class SequentialTokenGenerator(TokenGenerator):
    """Predictable tokens: session-1, csrf-1, session-2, csrf-2, ..."""

    def __init__(self) -> None:
        self._counter = 0

    def new_token(self) -> str:
        self._counter += 1
        return f"token-{self._counter}"


class FakeSessionStore(SessionStore):
    """In-memory auth_sessions keyed by token hash."""

    def __init__(self) -> None:
        self._rows: dict[uuid.UUID, AuthSession] = {}

    def create(self, session: AuthSession) -> None:
        self._rows[session.id] = session

    def find_active_by_token_hash(self, token_hash: str, now: datetime) -> AuthSession | None:
        for row in self._rows.values():
            if row.token_hash == token_hash and not row.is_expired(now):
                return row
        return None

    def delete(self, session_id: uuid.UUID) -> None:
        self._rows.pop(session_id, None)

    def set_organization(self, session_id: uuid.UUID, org_id: uuid.UUID) -> None:
        row = self._rows[session_id]
        self._rows[session_id] = AuthSession(
            id=row.id,
            user_id=row.user_id,
            token_hash=row.token_hash,
            csrf_token_hash=row.csrf_token_hash,
            organization_id=org_id,
            created_at=row.created_at,
            last_seen_at=row.last_seen_at,
            expires_at=row.expires_at,
        )

    def touch(self, session_id: uuid.UUID, now: datetime) -> None:
        row = self._rows[session_id]
        self._rows[session_id] = AuthSession(
            id=row.id,
            user_id=row.user_id,
            token_hash=row.token_hash,
            csrf_token_hash=row.csrf_token_hash,
            organization_id=row.organization_id,
            created_at=row.created_at,
            last_seen_at=now,
            expires_at=row.expires_at,
        )

    def delete_expired_for_user(self, user_id: uuid.UUID, now: datetime) -> None:
        expired = [
            sid for sid, row in self._rows.items() if row.user_id == user_id and row.is_expired(now)
        ]
        for sid in expired:
            del self._rows[sid]

    def all_rows(self) -> list[AuthSession]:
        return list(self._rows.values())


class FakeCredentialReader(CredentialReader):
    def __init__(self) -> None:
        self._rows: dict[str, tuple[User, str]] = {}

    def add(self, user: User, password_hash: str) -> None:
        self._rows[user.email] = (user, password_hash)

    def get_credentials_by_email(self, email: str) -> tuple[User, str] | None:
        return self._rows.get(email.lower().strip())


class FakeUserAccountReader(UserAccountReader):
    def __init__(self) -> None:
        self._users: dict[uuid.UUID, User] = {}

    def add(self, user: User) -> None:
        self._users[user.id] = user

    def get_active_user(self, user_id: uuid.UUID) -> User | None:
        user = self._users.get(user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            return None
        return user


class FakeTenantScope(TenantScopeSetter):
    def __init__(self) -> None:
        self.tenants: list[uuid.UUID] = []

    def set_tenant(self, organization_id: uuid.UUID) -> None:
        self.tenants.append(organization_id)


class FakeMembershipReader(MembershipReader):
    """Returns a fixed list for any user (or per-user lists keyed by user id)."""

    def __init__(self, rows: list[Membership] | None = None) -> None:
        self._rows = rows or []

    def list_for_user(self, user_id: uuid.UUID) -> list[Membership]:
        return [m for m in self._rows if m.user_id == user_id]


def make_auth_session(
    *,
    id: uuid.UUID | None = None,
    user_id: uuid.UUID,
    token_hash: str,
    csrf_token_hash: str,
    organization_id: uuid.UUID | None,
    created_at: datetime,
    expires_at: datetime,
) -> AuthSession:
    return AuthSession(
        id=id or uuid.uuid4(),
        user_id=user_id,
        token_hash=token_hash,
        csrf_token_hash=csrf_token_hash,
        organization_id=organization_id,
        created_at=created_at,
        last_seen_at=created_at,
        expires_at=expires_at,
    )


class FakeOrganizationRepositoryWithList(FakeOrganizationRepository):
    """Adds the Phase 2 ``list_by_ids`` read to the in-memory org repo."""

    def list_by_ids(self, org_ids: list[uuid.UUID]) -> list[Organization]:
        wanted = set(org_ids)
        found = [org for org in self._by_id.values() if org.id in wanted]
        # Preserve the caller's order, like the SQL adapter.
        by_id = {org.id: org for org in found}
        return [by_id[org_id] for org_id in org_ids if org_id in by_id]


class FakeMembershipRepositoryWithUsers(FakeMembershipRepository):
    """Adds the Phase 2 reads: per-user listing and the member list with emails."""

    def __init__(self) -> None:
        super().__init__()
        self.emails: dict[uuid.UUID, str] = {}

    def set_email(self, user_id: uuid.UUID, email: str) -> None:
        self.emails[user_id] = email

    def list_for_user(self, user_id: uuid.UUID) -> list[Membership]:
        rows = [m for m in self._rows if m.user_id == user_id]
        return sorted(rows, key=lambda m: m.created_at)

    def list_members_with_users(self, org_id: uuid.UUID) -> list[MemberSummary]:
        return [
            MemberSummary(
                membership_id=m.id,
                user_id=m.user_id,
                email=self.emails.get(m.user_id, "-"),
                role=m.role,
                status=m.status,
                created_at=m.created_at,
            )
            for m in self._rows
            if m.organization_id == org_id
        ]
