"""Unit tests for the Phase 2 authentication use cases (no database).

Covers the session security model end to end with fakes: uniform 401s, the CSRF
binding, the default-organization choice, org switching authorization, slug
derivation for signup, and expiry behaviour. The live RLS behaviour of the same
paths is proven separately by tests/integration/test_auth_live.py.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from marketpulse.application.services.audit import AuditService
from marketpulse.application.services.auth import AuthenticationService, resolve_session
from marketpulse.application.services.provisioning import TenantProvisioningService
from marketpulse.application.services.signup import SignupService
from marketpulse.application.services.workspaces import WorkspaceService
from marketpulse.core.cookies import hash_token
from marketpulse.core.errors import AppError
from tests.fakes import (
    FakeClock,
    FakeCredentialReader,
    FakeMembershipReader,
    FakeMembershipRepository,
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


def auth_doubles() -> tuple[FakeCredentialReader, FakeMembershipReader, FakeUserAccountReader]:
    """The three auth doubles most login/switch tests need."""
    return FakeCredentialReader(), FakeMembershipReader(), FakeUserAccountReader()


LIFETIME = timedelta(hours=168)
PASSWORD = "correct-horse-battery"


def make_auth_service(
    *,
    memberships: FakeMembershipReader | None = None,
    credentials: FakeCredentialReader | None = None,
    store: FakeSessionStore | None = None,
    organizations: FakeOrganizationRepositoryWithList | None = None,
    now: datetime = NOW,
) -> tuple[AuthenticationService, FakeSessionStore, FakeTenantScope, FakePasswordHasher]:
    creds = credentials or FakeCredentialReader()
    reader = memberships or FakeMembershipReader()
    rows = store or FakeSessionStore()
    orgs = organizations or FakeOrganizationRepositoryWithList()
    scope = FakeTenantScope()
    hasher = FakePasswordHasher()
    service = AuthenticationService(
        credentials=creds,
        sessions=rows,
        memberships=reader,
        organizations=orgs,
        users=FakeUserAccountReader(),
        tenant_scope=scope,
        hasher=hasher,
        tokens=SequentialTokenGenerator(),
        clock=FakeClock(now),
        session_lifetime=LIFETIME,
    )
    return service, rows, scope, hasher


def make_signup_service() -> tuple[
    SignupService, FakeOrganizationRepositoryWithList, FakeUserRepository, RecordingAuditWriter
]:
    orgs = FakeOrganizationRepositoryWithList()
    users = FakeUserRepository()
    audit = RecordingAuditWriter()
    clock = FakeClock(NOW)
    provisioning = TenantProvisioningService(
        orgs, users, FakeMembershipRepository(), AuditService(audit), clock
    )
    workspaces = WorkspaceService(FakeWorkspaceRepository(), AuditService(audit), clock)
    return SignupService(provisioning, workspaces, orgs), orgs, users, audit


# --- signup ---
def test_signup_creates_org_user_membership_workspace_and_audits() -> None:
    signup, orgs, users, audit = make_signup_service()
    org, user = signup.register(
        email="Owner@Example.com ", password=PASSWORD, organization_name="Acme Ltd"
    )
    assert org.slug == "acme-ltd"
    assert user.email == "owner@example.com"
    assert orgs.get_by_slug("acme-ltd") is not None
    assert users.get_by_email("owner@example.com") is not None
    actions = [e["action"].value for e in audit.events]
    assert "organization.created" in actions
    assert "membership.added" in actions
    assert "workspace.created" in actions


def test_signup_derives_a_unique_slug_with_suffix_on_collision() -> None:
    signup, orgs, _, _ = make_signup_service()
    first, _ = signup.register(email="a@x.test", password=PASSWORD, organization_name="Acme")
    second, _ = signup.register(email="b@x.test", password=PASSWORD, organization_name="Acme")
    assert first.slug == "acme"
    assert second.slug == "acme-2"
    assert orgs.get_by_slug("acme-2") is not None


def test_signup_rejects_a_short_password_with_422() -> None:
    signup, *_ = make_signup_service()
    with pytest.raises(AppError) as excinfo:
        signup.register(email="a@x.test", password="short", organization_name="Acme")
    assert excinfo.value.status_code == 422


def test_signup_rejects_an_invalid_email_with_422() -> None:
    signup, *_ = make_signup_service()
    with pytest.raises(AppError) as excinfo:
        signup.register(email="not-an-email", password=PASSWORD, organization_name="Acme")
    assert excinfo.value.status_code == 422


def test_signup_rejects_a_duplicate_email_with_409() -> None:
    signup, *_ = make_signup_service()
    signup.register(email="a@x.test", password=PASSWORD, organization_name="Acme")
    with pytest.raises(AppError) as excinfo:
        signup.register(email="A@X.TEST", password=PASSWORD, organization_name="Other")
    assert excinfo.value.status_code == 409


# --- login ---
def seed_user(
    creds: FakeCredentialReader,
    memberships: FakeMembershipReader,
    account_reader: FakeUserAccountReader,
    *,
    org_ids: list[uuid.UUID],
    status: object = None,
) -> object:
    from marketpulse.domain.tenancy import UserStatus

    user = make_user(email="owner@example.com", status=status or UserStatus.ACTIVE)
    creds.add(user, f"fakehash::{PASSWORD[::-1]}")
    account_reader.add(user)
    for org_id in org_ids:
        memberships._rows.append(  # noqa: SLF001 - tests seed the double
            make_membership(organization_id=org_id, user_id=user.id)
        )
    return user


def test_login_success_creates_a_session_and_picks_the_first_membership() -> None:
    creds, memberships, account = auth_doubles()
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    user = seed_user(creds, memberships, account, org_ids=[org_b, org_a])
    # Make org_a the OLDEST active membership so it becomes the default.
    memberships._rows.reverse()  # noqa: SLF001
    service, store, scope, _ = make_auth_service(memberships=memberships, credentials=creds)
    outcome = service.login(email="Owner@Example.com", password=PASSWORD)
    assert outcome.user.id == user.id
    assert outcome.tokens.session.organization_id == org_a
    assert outcome.tokens.session.expires_at - outcome.tokens.session.created_at == LIFETIME
    # The stored hashes match the cookie material exactly (digest binding).
    assert outcome.tokens.session.token_hash == hash_token(outcome.tokens.session_token)
    assert outcome.tokens.session.csrf_token_hash == hash_token(outcome.tokens.csrf_token)
    assert len(store.all_rows()) == 1


def test_login_wrong_password_is_uniform_401() -> None:
    creds, memberships, account = auth_doubles()
    seed_user(creds, memberships, account, org_ids=[uuid.uuid4()])
    service, *_ = make_auth_service(memberships=memberships, credentials=creds)
    with pytest.raises(AppError) as excinfo:
        service.login(email="owner@example.com", password="wrong-password")
    assert excinfo.value.status_code == 401


def test_login_unknown_email_matches_wrong_password_message_exactly() -> None:
    service, *_ = make_auth_service()
    with pytest.raises(AppError) as unknown:
        service.login(email="nobody@x.test", password=PASSWORD)
    creds, memberships, account = auth_doubles()
    seed_user(creds, memberships, account, org_ids=[uuid.uuid4()])
    service2, *_ = make_auth_service(memberships=memberships, credentials=creds)
    with pytest.raises(AppError) as wrongpw:
        service2.login(email="owner@example.com", password="totally-wrong")
    assert unknown.value.message == wrongpw.value.message
    assert unknown.value.status_code == wrongpw.value.status_code == 401


def test_login_disabled_user_is_uniform_401() -> None:
    from marketpulse.domain.tenancy import UserStatus

    creds, memberships, account = auth_doubles()
    seed_user(creds, memberships, account, org_ids=[uuid.uuid4()], status=UserStatus.DISABLED)
    service, *_ = make_auth_service(memberships=memberships, credentials=creds)
    with pytest.raises(AppError) as excinfo:
        service.login(email="owner@example.com", password=PASSWORD)
    assert excinfo.value.status_code == 401


def test_login_without_active_membership_is_403() -> None:
    from marketpulse.domain.tenancy import MembershipStatus

    creds, memberships, account = auth_doubles()
    seed_user(creds, memberships, account, org_ids=[uuid.uuid4()])
    # Turn the only membership into an INVITED one (not active).
    memberships._rows[0] = make_membership(  # noqa: SLF001
        organization_id=memberships._rows[0].organization_id,  # noqa: SLF001
        user_id=memberships._rows[0].user_id,  # noqa: SLF001
        status=MembershipStatus.INVITED,
    )
    service, *_ = make_auth_service(memberships=memberships, credentials=creds)
    with pytest.raises(AppError) as excinfo:
        service.login(email="owner@example.com", password=PASSWORD)
    assert excinfo.value.status_code == 403


def test_login_garbage_collects_expired_sessions() -> None:
    from marketpulse.domain.entities import AuthSession

    creds, memberships, account = auth_doubles()
    user = seed_user(creds, memberships, account, org_ids=[uuid.uuid4()])
    service, store, *_ = make_auth_service(memberships=memberships, credentials=creds)
    stale = AuthSession(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=hash_token("stale-token"),
        csrf_token_hash=hash_token("stale-csrf"),
        organization_id=uuid.uuid4(),
        created_at=NOW - timedelta(days=30),
        last_seen_at=NOW - timedelta(days=30),
        expires_at=NOW - timedelta(minutes=1),  # already expired at NOW
    )
    store.create(stale)
    service.login(email="owner@example.com", password=PASSWORD)
    assert all(row.id != stale.id for row in store.all_rows())


# --- logout ---
def test_logout_with_valid_csrf_deletes_the_session() -> None:
    service, store, *_ = make_auth_service()
    tokens = service.start_session(user_id=uuid.uuid4(), organization_id=uuid.uuid4())
    service.logout(session_token=tokens.session_token, csrf_token=tokens.csrf_token)
    assert store.all_rows() == []


def test_logout_with_wrong_csrf_is_403() -> None:
    service, store, *_ = make_auth_service()
    tokens = service.start_session(user_id=uuid.uuid4(), organization_id=uuid.uuid4())
    with pytest.raises(AppError) as excinfo:
        service.logout(session_token=tokens.session_token, csrf_token="forged-token")
    assert excinfo.value.status_code == 403
    assert len(store.all_rows()) == 1  # the session survives a forged attempt


def test_logout_without_a_session_is_401() -> None:
    service, *_ = make_auth_service()
    with pytest.raises(AppError) as excinfo:
        service.logout(session_token="", csrf_token=None)
    assert excinfo.value.status_code == 401


# --- switch organization ---
def test_switch_to_a_member_org_updates_the_session_and_sets_scope() -> None:
    creds, memberships, account = auth_doubles()
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    user = seed_user(creds, memberships, account, org_ids=[org_a])
    memberships._rows.append(make_membership(organization_id=org_b, user_id=user.id))  # noqa: SLF001
    orgs = FakeOrganizationRepositoryWithList()
    orgs.add(make_organization(id=org_a, slug="a"))
    orgs.add(make_organization(id=org_b, slug="b"))
    service, store, scope, _ = make_auth_service(
        memberships=memberships, credentials=creds, organizations=orgs
    )
    tokens = service.start_session(user_id=user.id, organization_id=org_a)
    org = service.switch_organization(
        session_token=tokens.session_token, csrf_token=tokens.csrf_token, organization_id=org_b
    )
    assert org.id == org_b
    assert scope.tenants == [org_b]
    assert store.all_rows()[0].organization_id == org_b


def test_switch_to_a_non_member_org_is_403() -> None:
    creds, memberships, account = auth_doubles()
    org_a = uuid.uuid4()
    user = seed_user(creds, memberships, account, org_ids=[org_a])
    service, store, scope, _ = make_auth_service(memberships=memberships, credentials=creds)
    tokens = service.start_session(user_id=user.id, organization_id=org_a)
    with pytest.raises(AppError) as excinfo:
        service.switch_organization(
            session_token=tokens.session_token,
            csrf_token=tokens.csrf_token,
            organization_id=uuid.uuid4(),
        )
    assert excinfo.value.status_code == 403
    # The active org is unchanged after a denied switch.
    assert store.all_rows()[0].organization_id == org_a
    assert scope.tenants == []


# --- resolve_session (the session resolver's core) ---
def _session_row(token: str, user_id: uuid.UUID, org_id: uuid.UUID | None) -> object:
    """A stored row for `token` (only its digest is stored, like production)."""
    from marketpulse.domain.entities import AuthSession

    return AuthSession(
        id=uuid.uuid4(),
        user_id=user_id,
        token_hash=hash_token(token),
        csrf_token_hash=hash_token(f"csrf::{token}"),
        organization_id=org_id,
        created_at=NOW,
        last_seen_at=NOW,
        expires_at=NOW + LIFETIME,
    )


def test_resolve_session_returns_the_identity_for_a_valid_cookie() -> None:
    from marketpulse.domain.tenancy import UserStatus

    store, account = FakeSessionStore(), FakeUserAccountReader()
    active = make_user(status=UserStatus.ACTIVE)
    account.add(active)
    org_id = uuid.uuid4()
    store.create(_session_row("good-token", active.id, org_id))

    resolution = resolve_session(
        sessions=store,
        users=account,
        session_token="good-token",
        clock=FakeClock(NOW + timedelta(minutes=5)),
    )
    assert resolution is not None
    assert resolution.user.id == active.id
    assert resolution.session.organization_id == org_id
    # last_seen_at was touched.
    assert store.all_rows()[0].last_seen_at > NOW


def test_resolve_session_rejects_expired_disabled_and_missing() -> None:
    from marketpulse.domain.tenancy import UserStatus

    store, account = FakeSessionStore(), FakeUserAccountReader()
    active = make_user(status=UserStatus.ACTIVE)
    account.add(active)
    disabled = make_user(email="disabled@x.test", status=UserStatus.DISABLED)
    account.add(disabled)

    store.create(_session_row("good-token", active.id, uuid.uuid4()))
    store.create(_session_row("disabled-token", disabled.id, uuid.uuid4()))
    # An expired row: created long ago, already past its absolute expiry.
    from marketpulse.domain.entities import AuthSession

    expired = AuthSession(
        id=uuid.uuid4(),
        user_id=active.id,
        token_hash=hash_token("expired-token"),
        csrf_token_hash=hash_token("csrf::expired"),
        organization_id=uuid.uuid4(),
        created_at=NOW - timedelta(days=30),
        last_seen_at=NOW - timedelta(days=30),
        expires_at=NOW - timedelta(minutes=1),
    )
    store.create(expired)

    clock = FakeClock(NOW)
    assert (
        resolve_session(sessions=store, users=account, session_token="good-token", clock=clock)
        is not None
    )
    assert (
        resolve_session(sessions=store, users=account, session_token="disabled-token", clock=clock)
        is None
    )
    assert (
        resolve_session(sessions=store, users=account, session_token="expired-token", clock=clock)
        is None
    )
    assert resolve_session(sessions=store, users=account, session_token=None, clock=clock) is None
    assert resolve_session(sessions=store, users=account, session_token="", clock=clock) is None
