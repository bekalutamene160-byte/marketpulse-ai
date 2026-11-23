"""Auth-backed tenant context resolver (Phase 2, replaces ADR-0024's header resolver).

Implements the SAME ``TenantContextResolver`` port as the dev header resolver, but
derives the context from the server-side session instead of trusting the client:
cookie -> ``auth_sessions`` row (by token digest, expiry-checked) -> user must be
active -> ``TenantContext(active_org, user)``.

Any failure (no cookie, unknown token, expired, disabled user, no active
organization) resolves to ``None``, which ``TenantContextService`` turns into a
uniform 401 — the same fail-closed contract as Phase 1, now backed by real
authentication. The dev header resolver remains available for local/test tooling
behind the explicit ``MP_ENABLE_DEV_TENANT_HEADER`` flag; the composition root wires
THIS resolver whenever a database is configured and the dev flag is off.
"""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy.orm import Session, sessionmaker

from marketpulse.application.ports.auth import SessionStore, UserAccountReader
from marketpulse.application.services.auth import resolve_session
from marketpulse.core.clock import Clock
from marketpulse.core.cookies import SESSION_COOKIE, parse_cookie_header
from marketpulse.core.tenancy import TenantContext
from marketpulse.infrastructure.db.auth import (
    SqlAlchemySessionStore,
    SqlAlchemyUserAccountReader,
)
from marketpulse.infrastructure.db.session import DatabaseSessionManager


def _cookie_header(headers: Mapping[str, str]) -> str:
    """Case-insensitive lookup of the raw Cookie header (Starlette lowercases keys)."""
    if "cookie" in headers:
        return headers["cookie"]
    if "Cookie" in headers:
        return headers["Cookie"]
    return ""


class SessionTenantContextResolver:
    """Resolves the acting tenant from the ``mp_session`` cookie, or None."""

    def __init__(self, session_factory: sessionmaker[Session], clock: Clock) -> None:
        self._session_factory = session_factory
        self._clock = clock

    def resolve(self, headers: Mapping[str, str]) -> TenantContext | None:
        cookies = parse_cookie_header(_cookie_header(headers))
        token = cookies.get(SESSION_COOKIE)
        if not token:
            return None
        # A short dedicated read: auth_sessions/users are global tables, so this
        # session deliberately sets NO tenant GUC (there is nothing to set yet).
        with self._session_factory() as session, session.begin():
            resolution = resolve_session(
                sessions=self._store(session),
                users=self._users_reader(session),
                session_token=token,
                clock=self._clock,
            )
            if resolution is None:
                return None
            if resolution.session.organization_id is None:
                # No active organization (e.g. the last membership vanished): fail
                # closed rather than act tenant-less.
                return None
            return TenantContext(
                organization_id=resolution.session.organization_id,
                user_id=resolution.session.user_id,
            )

    def _store(self, session: Session) -> SessionStore:
        return SqlAlchemySessionStore(session)

    def _users_reader(self, session: Session) -> UserAccountReader:
        return SqlAlchemyUserAccountReader(session)


def build_session_resolver(
    manager: DatabaseSessionManager, clock: Clock
) -> SessionTenantContextResolver:
    """Composition-root convenience: resolver over the application-role manager."""
    return SessionTenantContextResolver(manager.session_factory, clock)
