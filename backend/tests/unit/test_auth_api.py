"""API tests for the authentication endpoints (Phase 2).

The HTTP contract is exercised for real through the FastAPI test client: cookie
flags, the CSRF requirement, the uniform 401, the 429 rate limit, and the /auth/me
data join. The service builders are monkeypatched to compose the SAME use cases on
in-memory fakes, so no database is needed; the live path is covered by
tests/integration/test_auth_live.py.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import marketpulse.api.v1.routers.auth as auth_router
from marketpulse.api.deps import (
    get_membership_repository,
    get_organization_repository,
    get_plain_session,
    get_priv_session,
    get_user_repository,
)
from marketpulse.application.services.audit import AuditService
from marketpulse.application.services.auth import AuthenticationService
from marketpulse.application.services.provisioning import TenantProvisioningService
from marketpulse.application.services.signup import SignupService
from marketpulse.application.services.workspaces import WorkspaceService
from marketpulse.config import Settings
from marketpulse.core.tenancy import TenantContext
from marketpulse.main import create_app
from tests.fakes import (
    FakeClock,
    FakeCredentialReader,
    FakeMembershipReader,
    FakeMembershipRepository,
    FakeMembershipRepositoryWithUsers,
    FakeOrganizationRepositoryWithList,
    FakePasswordHasher,
    FakeSessionStore,
    FakeTenantScope,
    FakeUserAccountReader,
    FakeUserRepository,
    FakeWorkspaceRepository,
    RecordingAuditWriter,
    SequentialTokenGenerator,
    make_membership,
    make_organization,
    make_user,
)

NOW = datetime(2026, 11, 21, 12, 0, 0, tzinfo=UTC)
PASSWORD = "correct-horse-battery"


class _NullSession:
    """Stand-in for the raw Session dependency: the fakes never touch it."""

    def begin(self) -> _NullSession:
        return self

    def __enter__(self) -> _NullSession:
        return self

    def __exit__(self, *args: object) -> bool:
        return False


def auth_app(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[
    TestClient,
    FakeSessionStore,
    FakeCredentialReader,
    FakeMembershipReader,
    FakeOrganizationRepositoryWithList,
]:
    """An app whose auth use cases run on in-memory doubles (no database)."""
    settings = Settings(
        _env_file=None,
        environment="test",
        log_level="WARNING",
        database_url=None,
        redis_url=None,
        auth_rate_limit_attempts=5,
    )
    app = create_app(settings)
    creds = FakeCredentialReader()
    memberships = FakeMembershipReader()
    store = FakeSessionStore()
    orgs_repo = FakeOrganizationRepositoryWithList()

    def fake_build_auth(session: object, cfg: object, clock: object) -> AuthenticationService:
        return AuthenticationService(
            credentials=creds,
            sessions=store,
            memberships=memberships,
            organizations=orgs_repo,
            users=FakeUserAccountReader(),
            tenant_scope=FakeTenantScope(),
            hasher=FakePasswordHasher(),
            tokens=SequentialTokenGenerator(),
            clock=FakeClock(NOW),
        )

    def fake_build_signup(session: object, clock: object) -> SignupService:
        audit = RecordingAuditWriter()
        orgs = FakeOrganizationRepositoryWithList()
        provisioning = TenantProvisioningService(
            orgs,
            FakeUserRepository(),
            FakeMembershipRepository(),
            AuditService(audit),
            FakeClock(NOW),
        )
        workspaces = WorkspaceService(
            FakeWorkspaceRepository(), AuditService(audit), FakeClock(NOW)
        )
        return SignupService(provisioning, workspaces, orgs)

    monkeypatch.setattr(auth_router, "build_auth_service", fake_build_auth)
    monkeypatch.setattr(auth_router, "build_signup_service", fake_build_signup)

    def fake_priv_session() -> Iterator[_NullSession]:
        yield _NullSession()

    def fake_plain_session() -> Iterator[_NullSession]:
        yield _NullSession()

    app.dependency_overrides[get_priv_session] = fake_priv_session
    app.dependency_overrides[get_plain_session] = fake_plain_session
    return TestClient(app), store, creds, memberships, orgs_repo


def seed_account(
    creds: FakeCredentialReader, memberships: FakeMembershipReader, *, org_ids: list[uuid.UUID]
) -> tuple[object, uuid.UUID]:
    user = make_user(email="owner@example.com")
    creds.add(user, "fakehash::" + PASSWORD[::-1])
    for org_id in org_ids:
        memberships._rows.append(make_membership(organization_id=org_id, user_id=user.id))  # noqa: SLF001
    return user, org_ids[0]


def test_register_returns_201_sets_cookies_and_returns_the_org(monkeypatch) -> None:
    client, store, _, _, _ = auth_app(monkeypatch)
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "owner@example.com", "password": PASSWORD, "organization_name": "Acme Ltd"},
    )
    assert r.status_code == 201
    assert r.json()["organization"]["slug"] == "acme-ltd"
    assert r.json()["user"]["email"] == "owner@example.com"
    set_cookie_header = r.headers["set-cookie"]
    assert "mp_session=" in set_cookie_header
    assert "HttpOnly" in set_cookie_header
    assert "SameSite=lax" in set_cookie_header
    assert "mp_csrf=" in set_cookie_header
    assert len(store.all_rows()) == 1


def test_register_rejects_a_short_password_with_422(monkeypatch) -> None:
    client, _, _, _, _ = auth_app(monkeypatch)
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "owner@example.com", "password": "short", "organization_name": "Acme"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_register_is_rate_limited_with_429(monkeypatch) -> None:
    client, _, _, _, _ = auth_app(monkeypatch)
    last_status = 0
    for attempt in range(6):
        r = client.post(
            "/api/v1/auth/register",
            json={
                "email": f"u{attempt}@example.com",
                "password": PASSWORD,
                "organization_name": "Acme",
            },
        )
        last_status = r.status_code
    assert last_status == 429
    again = client.post(
        "/api/v1/auth/register",
        json={"email": "u99@example.com", "password": PASSWORD, "organization_name": "Acme"},
    )
    assert again.json()["error"]["code"] == "RATE_LIMITED"


def test_login_sets_cookies_and_wrong_password_is_uniform_401(monkeypatch) -> None:
    client, _, creds, memberships, orgs_repo = auth_app(monkeypatch)
    org_id = uuid.uuid4()
    seed_account(creds, memberships, org_ids=[org_id])

    ok = client.post(
        "/api/v1/auth/login", json={"email": "owner@example.com", "password": PASSWORD}
    )
    assert ok.status_code == 200
    assert ok.json()["organization_id"] == str(org_id)
    assert "mp_session=" in ok.headers["set-cookie"]

    bad = client.post(
        "/api/v1/auth/login", json={"email": "owner@example.com", "password": "wrong-password"}
    )
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "UNAUTHORIZED"


def test_logout_requires_the_csrf_token(monkeypatch) -> None:
    client, store, creds, memberships, _ = auth_app(monkeypatch)
    seed_account(creds, memberships, org_ids=[uuid.uuid4()])
    client.post("/api/v1/auth/login", json={"email": "owner@example.com", "password": PASSWORD})

    forged = client.post("/api/v1/auth/logout")
    assert forged.status_code == 403
    assert len(store.all_rows()) == 1  # a forged logout does not revoke

    csrf = client.cookies.get("mp_csrf", "")
    ok = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
    assert ok.status_code == 204
    assert store.all_rows() == []


def test_switch_organization_requires_csrf_and_membership(monkeypatch) -> None:
    client, _, creds, memberships, orgs_repo = auth_app(monkeypatch)
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    seed_account(creds, memberships, org_ids=[org_a, org_b])
    orgs_repo.add(make_organization(id=org_a, slug="a"))
    orgs_repo.add(make_organization(id=org_b, slug="b"))
    client.post("/api/v1/auth/login", json={"email": "owner@example.com", "password": PASSWORD})
    csrf = client.cookies.get("mp_csrf", "")

    forged = client.post("/api/v1/auth/switch-organization", json={"organization_id": str(org_b)})
    assert forged.status_code == 403

    ok = client.post(
        "/api/v1/auth/switch-organization",
        json={"organization_id": str(org_b)},
        headers={"X-CSRF-Token": csrf},
    )
    assert ok.status_code == 200
    assert ok.json()["organization"]["id"] == str(org_b)

    stranger = client.post(
        "/api/v1/auth/switch-organization",
        json={"organization_id": str(uuid.uuid4())},
        headers={"X-CSRF-Token": csrf},
    )
    assert stranger.status_code == 403


class _FixedResolver:
    """A resolver double returning a fixed context (or None to simulate no cookie)."""

    def __init__(self, ctx: TenantContext | None) -> None:
        self._ctx = ctx

    def resolve(self, headers: object) -> TenantContext | None:
        return self._ctx


class _StaticUserRepo:
    def __init__(self, user: object) -> None:
        self._user = user

    def get(self, user_id: uuid.UUID) -> object | None:
        return self._user if self._user.id == user_id else None  # type: ignore[attr-defined]

    def add(self, user: object, password_hash: str) -> None:  # pragma: no cover
        raise NotImplementedError

    def get_by_email(self, email: str) -> None:  # pragma: no cover
        raise NotImplementedError


def me_app(
    ctx: TenantContext | None, *, other_org_ids: list[uuid.UUID] | None = None
) -> TestClient:
    """An app with a fixed tenant context and in-memory /auth/me repositories.

    The seeded organizations derive from the CONTEXT's organization (the active one)
    plus ``other_org_ids``, so the caller controls the ids end to end.
    """
    settings = Settings(
        _env_file=None, environment="test", log_level="WARNING", database_url=None, redis_url=None
    )
    user = make_user(email="owner@example.com")
    org_a = ctx.organization_id if ctx is not None else uuid.uuid4()
    extra = [uuid.uuid4()] if other_org_ids is None and ctx is not None else (other_org_ids or [])
    if ctx is not None:
        ctx = TenantContext(organization_id=org_a, user_id=user.id)
    app: FastAPI = create_app(settings, tenant_resolver=_FixedResolver(ctx))
    memberships_repo = FakeMembershipRepositoryWithUsers()
    memberships_repo.add(make_membership(organization_id=org_a, user_id=user.id))
    for org_id in extra:
        memberships_repo.add(make_membership(organization_id=org_id, user_id=user.id))
    memberships_repo.set_email(user.id, "owner@example.com")
    orgs_repo = FakeOrganizationRepositoryWithList()
    orgs_repo.add(make_organization(id=org_a, slug="a"))
    for org_id in extra:
        orgs_repo.add(make_organization(id=org_id, slug=f"org-{str(org_id)[:6]}"))
    app.dependency_overrides[get_user_repository] = lambda: _StaticUserRepo(user)
    app.dependency_overrides[get_membership_repository] = lambda: memberships_repo
    app.dependency_overrides[get_organization_repository] = lambda: orgs_repo
    return TestClient(app)


def test_me_requires_a_session() -> None:
    assert me_app(None).get("/api/v1/auth/me").status_code == 401


def test_me_returns_the_user_active_org_and_all_memberships() -> None:
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    client = me_app(TenantContext(organization_id=org_a), other_org_ids=[org_b])
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["email"] == "owner@example.com"
    assert body["active_organization"]["id"] == str(org_a)
    assert {m["organization_id"] for m in body["memberships"]} == {str(org_a), str(org_b)}


def test_members_endpoint_returns_the_current_tenant_only() -> None:
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    user = make_user(email="owner@example.com")
    colleague = make_user(email="colleague@example.com")
    settings = Settings(
        _env_file=None, environment="test", log_level="WARNING", database_url=None, redis_url=None
    )
    app = create_app(settings, tenant_resolver=_FixedResolver(TenantContext(organization_id=org_a)))
    memberships_repo = FakeMembershipRepositoryWithUsers()
    memberships_repo.add(make_membership(organization_id=org_a, user_id=user.id))
    memberships_repo.add(make_membership(organization_id=org_a, user_id=colleague.id))
    memberships_repo.add(make_membership(organization_id=org_b, user_id=colleague.id))
    memberships_repo.set_email(user.id, "owner@example.com")
    memberships_repo.set_email(colleague.id, "colleague@example.com")
    app.dependency_overrides[get_membership_repository] = lambda: memberships_repo
    app.dependency_overrides[get_organization_repository] = lambda: (
        FakeOrganizationRepositoryWithList()
    )

    r = TestClient(app).get("/api/v1/organizations/members")
    assert r.status_code == 200
    assert {m["email"] for m in r.json()} == {"owner@example.com", "colleague@example.com"}
