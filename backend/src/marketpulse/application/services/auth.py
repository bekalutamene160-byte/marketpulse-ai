"""Use cases: authentication sessions (login, logout, switch) — Phase 2.

The service owns session semantics only. Account CREATION is a separate use case
(``SignupService``, which reuses ``TenantProvisioningService`` under the privileged
connection, because row-level security makes it impossible for the application role
to create an organization whose id it cannot yet know — see that service's docstring
and ADR-0023).

Session security model (blueprint 15.1, ADR-0025):

- The browser holds an opaque random token (HttpOnly cookie). Only the SHA-256
  digest of the token is persisted, so a stolen database dump cannot be replayed.
- Sessions have an ABSOLUTE expiry (no sliding renewal): predictable, and a stolen
  cookie dies with the session.
- The CSRF token is a separate random value bound to the session row by digest; every
  authenticated state change must present it (double-submit + server-side check).
- Wrong email, wrong password and disabled accounts produce the SAME error (uniform
  401): nothing about the response tells an attacker which part failed.
- A user whose password verifies but who has no ACTIVE membership cannot act: 403.
  Membership absence is authorization, not authentication, so it is safe to differ.
- Expired sessions of a user are garbage-collected opportunistically at login.
- Login/logout are recorded as structured logs, not audit rows: ``audit_events`` is
  tenant-scoped (RLS WITH CHECK requires ``app.tenant_id``), and a login has no
  tenant until the default organization is chosen; the tenant-agnostic history of
  auth actions arrives with the observability/audit phase (13). Registration DOES
  write the normal tenant audit rows, because it creates them with the organization.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from marketpulse.application.ports.auth import (
    CredentialReader,
    MembershipReader,
    PasswordHasher,
    SessionStore,
    TenantScopeSetter,
    UserAccountReader,
)
from marketpulse.application.ports.repositories import OrganizationRepository
from marketpulse.core.clock import Clock
from marketpulse.core.cookies import hash_token, token_hashes_match
from marketpulse.core.errors import AppError, ErrorCode
from marketpulse.core.ids import new_id
from marketpulse.domain.entities import AuthSession, Organization, User
from marketpulse.domain.tenancy import MembershipStatus, UserStatus

logger = logging.getLogger("marketpulse.auth")

#: How long a login token stays valid. Configurable via Settings in the API layer;
#: the service receives the lifetime so tests can pin it.
DEFAULT_SESSION_LIFETIME = timedelta(hours=168)  # 7 days

_LOGIN_FAILURE_MESSAGE = "Email or password is incorrect."


class TokenGenerator(Protocol):
    """Produces opaque, high-entropy cookie material (adapter: ``secrets``)."""

    def new_token(self) -> str: ...


@dataclass(frozen=True, slots=True)
class SessionTokens:
    """The one-time plaintext cookie material for a new session. Never logged, never stored."""

    session: AuthSession
    session_token: str
    csrf_token: str


@dataclass(frozen=True, slots=True)
class SessionResolution:
    """The outcome of resolving a cookie into an acting identity (or nothing)."""

    session: AuthSession
    user: User


@dataclass(frozen=True, slots=True)
class LoginOutcome:
    """Everything the login handler needs: who logged in and the cookie material."""

    user: User
    tokens: SessionTokens


class AuthenticationService:
    def __init__(
        self,
        *,
        credentials: CredentialReader,
        sessions: SessionStore,
        memberships: MembershipReader,
        organizations: OrganizationRepository,
        users: UserAccountReader,
        tenant_scope: TenantScopeSetter,
        hasher: PasswordHasher,
        tokens: TokenGenerator,
        clock: Clock,
        session_lifetime: timedelta = DEFAULT_SESSION_LIFETIME,
    ) -> None:
        self._credentials = credentials
        self._sessions = sessions
        self._memberships = memberships
        self._organizations = organizations
        self._users = users
        self._scope = tenant_scope
        self._hasher = hasher
        self._tokens = tokens
        self._clock = clock
        self._lifetime = session_lifetime

    # --- session creation (shared by login and signup) ---
    def start_session(
        self, *, user_id: uuid.UUID, organization_id: uuid.UUID | None
    ) -> SessionTokens:
        now = self._clock.utcnow()
        session_token = self._tokens.new_token()
        csrf_token = self._tokens.new_token()
        session = AuthSession(
            id=new_id(),
            user_id=user_id,
            token_hash=hash_token(session_token),
            csrf_token_hash=hash_token(csrf_token),
            organization_id=organization_id,
            created_at=now,
            last_seen_at=now,
            expires_at=now + self._lifetime,
        )
        # Opportunistic GC: this user's already-expired sessions are dead weight.
        self._sessions.delete_expired_for_user(user_id, now)
        self._sessions.create(session)
        return SessionTokens(session, session_token, csrf_token)

    # --- login ---
    def login(self, *, email: str, password: str) -> LoginOutcome:
        email = email.strip().lower()
        creds = self._credentials.get_credentials_by_email(email)
        if creds is None:
            raise AppError(
                ErrorCode.UNAUTHORIZED,
                _LOGIN_FAILURE_MESSAGE,
                status_code=401,
                diagnostic=f"no credentials for email={email}",
            )
        user, password_hash = creds
        if not self._hasher.verify(password_hash, password):
            raise AppError(
                ErrorCode.UNAUTHORIZED,
                _LOGIN_FAILURE_MESSAGE,
                status_code=401,
                diagnostic=f"password mismatch for user={user.id}",
            )
        if user.status != UserStatus.ACTIVE:
            # Same message as a wrong password: a disabled account must not be
            # distinguishable from a bad credential by a would-be attacker.
            raise AppError(
                ErrorCode.UNAUTHORIZED,
                _LOGIN_FAILURE_MESSAGE,
                status_code=401,
                diagnostic=f"user {user.id} is {user.status.value}",
            )
        # The plain session has no tenant context; the membership adapter establishes
        # the per-user scope itself (app.user_id, ADR-0026) before reading.
        memberships = self._memberships.list_for_user(user.id)
        active = [m for m in memberships if m.status == MembershipStatus.ACTIVE]
        if not active:
            raise AppError(
                ErrorCode.FORBIDDEN,
                "Your account has no active organization membership.",
                status_code=403,
                diagnostic=f"user {user.id} has no active membership",
            )
        default_org = active[0].organization_id
        tokens = self.start_session(user_id=user.id, organization_id=default_org)
        if self._hasher.needs_rehash(password_hash):
            # Persisted re-hash is deferred (no UPDATE grant on users, ADR-0025);
            # parameters only drift if the code constants are raised on purpose.
            logger.warning("password hash needs rehash user_id=%s", user.id)
        logger.info("login succeeded user_id=%s organization_id=%s", user.id, default_org)
        return LoginOutcome(user=user, tokens=tokens)

    # --- logout ---
    def logout(self, *, session_token: str, csrf_token: str | None) -> None:
        """Revoke the session presented by cookie; verify the CSRF binding first.

        Unknown/expired sessions raise 401 (nothing to log out); a known session
        with a missing or wrong CSRF token raises 403 (the request may be forged).
        """
        session = self._require_session(session_token)
        self._require_csrf(session, csrf_token)
        self._sessions.delete(session.id)
        logger.info("logout user_id=%s session_id=%s", session.user_id, session.id)

    # --- organization switching (the workspace selector) ---
    def switch_organization(
        self, *, session_token: str, csrf_token: str | None, organization_id: uuid.UUID
    ) -> Organization:
        session = self._require_session(session_token)
        self._require_csrf(session, csrf_token)
        memberships = self._memberships.list_for_user(session.user_id)
        membership = next(
            (
                m
                for m in memberships
                if m.organization_id == organization_id and m.status == MembershipStatus.ACTIVE
            ),
            None,
        )
        if membership is None:
            raise AppError(
                ErrorCode.FORBIDDEN,
                "You are not a member of that organization.",
                status_code=403,
                diagnostic=(
                    f"user {session.user_id} has no active membership in {organization_id}"
                ),
            )
        # Establish the tenant scope so the organization row (RLS, ADR-0022) is
        # readable in this same plain session, then persist the choice.
        self._scope.set_tenant(organization_id)
        org = self._organizations.get(organization_id)
        if org is None:
            # Membership exists but the org row is gone: an inconsistent state that
            # RLS surfaces honestly rather than hiding.
            raise AppError(
                ErrorCode.NOT_FOUND,
                "Organization was not found.",
                status_code=404,
                diagnostic=f"organization {organization_id} not visible after membership check",
            )
        self._sessions.set_organization(session.id, organization_id)
        logger.info(
            "switch organization user_id=%s session_id=%s -> %s",
            session.user_id,
            session.id,
            organization_id,
        )
        return org

    # --- helpers ---
    def _require_session(self, session_token: str) -> AuthSession:
        if not session_token:
            raise AppError(
                ErrorCode.UNAUTHORIZED,
                "Authentication is required to access this resource.",
                status_code=401,
                diagnostic="no session cookie presented",
            )
        session = self._sessions.find_active_by_token_hash(
            hash_token(session_token), self._clock.utcnow()
        )
        if session is None:
            raise AppError(
                ErrorCode.UNAUTHORIZED,
                "Authentication is required to access this resource.",
                status_code=401,
                diagnostic="no active session for the presented cookie",
            )
        return session

    def _require_csrf(self, session: AuthSession, presented: str | None) -> None:
        if presented is None or not token_hashes_match(presented, session.csrf_token_hash):
            raise AppError(
                ErrorCode.FORBIDDEN,
                "The request is missing a valid CSRF token.",
                status_code=403,
                diagnostic=f"csrf mismatch for session {session.id}",
            )


def resolve_session(
    *,
    sessions: SessionStore,
    users: UserAccountReader,
    session_token: str | None,
    clock: Clock,
) -> SessionResolution | None:
    """Cookie -> active session + active user, or None (uniform, no detail leaks).

    Shared by the session resolver adapter and any caller that must turn a presented
    token into an acting identity. Expiry is enforced by the store lookup; a disabled
    user kills the session immediately even though its row is still unexpired.
    """
    if not session_token:
        return None
    session = sessions.find_active_by_token_hash(hash_token(session_token), clock.utcnow())
    if session is None:
        return None
    user = users.get_active_user(session.user_id)
    if user is None:
        return None
    sessions.touch(session.id, clock.utcnow())
    return SessionResolution(session, user)
