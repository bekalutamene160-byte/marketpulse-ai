"""Unit tests for the session tenant resolver (cookie -> context or None).

The resolver is exercised with a fake session factory and overridden store/user
adapters, so the cookie-parsing and fail-closed logic is proven without a database.
The real database behaviour (expiry SQL, disabled user) is covered by the service
tests and the live integration test.
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime, timedelta

from marketpulse.core.tenancy import TenantContext
from marketpulse.infrastructure.tenancy.session_resolver import SessionTenantContextResolver
from tests.fakes import (
    FakeClock,
    FakeSessionStore,
    FakeUserAccountReader,
    make_user,
)

NOW = datetime(2026, 11, 21, 12, 0, 0, tzinfo=UTC)


class _FakeSessionCtx:
    def __enter__(self) -> _FakeSessionCtx:
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def begin(self) -> contextlib.AbstractContextIterator:
        return contextlib.nullcontext()  # type: ignore[return-value]


class _FakeSessionFactory:
    def __call__(self) -> _FakeSessionCtx:
        return _FakeSessionCtx()


class _StubResolver(SessionTenantContextResolver):
    """Overrides the two adapter hooks with fakes; the flow itself runs for real."""

    def __init__(self, store: FakeSessionStore, account: FakeUserAccountReader) -> None:
        super().__init__(_FakeSessionFactory(), FakeClock(NOW))  # type: ignore[arg-type]
        self._fake_store = store
        self._fake_account = account

    def _store(self, session: object) -> FakeSessionStore:  # noqa: ARG002
        return self._fake_store

    def _users_reader(self, session: object) -> FakeUserAccountReader:  # noqa: ARG002
        return self._fake_account


def _cookie_header(value: str) -> dict[str, str]:
    return {"cookie": f"mp_session={value}; other=1"}


def test_resolves_the_tenant_context_from_a_valid_cookie() -> None:
    from marketpulse.core.cookies import hash_token
    from marketpulse.core.ids import new_id
    from marketpulse.domain.entities import AuthSession
    from marketpulse.domain.tenancy import UserStatus

    store, account = FakeSessionStore(), FakeUserAccountReader()
    org_id = uuid.uuid4()
    user = make_user(status=UserStatus.ACTIVE)
    account.add(user)
    store.create(
        AuthSession(
            id=new_id(),
            user_id=user.id,
            token_hash=hash_token("cookie-token"),
            csrf_token_hash=hash_token("csrf"),
            organization_id=org_id,
            created_at=NOW,
            last_seen_at=NOW,
            expires_at=NOW + timedelta(hours=1),
        )
    )
    resolver = _StubResolver(store, account)
    ctx = resolver.resolve(_cookie_header("cookie-token"))
    assert ctx == TenantContext(organization_id=org_id, user_id=user.id)


def test_missing_or_malformed_cookie_resolves_to_none() -> None:
    resolver = _StubResolver(FakeSessionStore(), FakeUserAccountReader())
    assert resolver.resolve({}) is None
    assert resolver.resolve({"cookie": "not-a-cookie"}) is None
    assert resolver.resolve(_cookie_header("")) is None
    assert resolver.resolve(_cookie_header("unknown-token")) is None


def test_a_session_without_an_organization_fails_closed() -> None:
    from marketpulse.core.cookies import hash_token
    from marketpulse.core.ids import new_id
    from marketpulse.domain.entities import AuthSession
    from marketpulse.domain.tenancy import UserStatus

    store, account = FakeSessionStore(), FakeUserAccountReader()
    user = make_user(status=UserStatus.ACTIVE)
    account.add(user)
    store.create(
        AuthSession(
            id=new_id(),
            user_id=user.id,
            token_hash=hash_token("orgless"),
            csrf_token_hash=hash_token("csrf"),
            organization_id=None,
            created_at=NOW,
            last_seen_at=NOW,
            expires_at=NOW + timedelta(hours=1),
        )
    )
    resolver = _StubResolver(store, account)
    assert resolver.resolve(_cookie_header("orgless")) is None
