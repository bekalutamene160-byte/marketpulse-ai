"""Unit tests for the tenant provisioning use case (admin/bootstrap path).

Provisioning runs against a privileged connection in production; here the fake
repositories stand in. The tests prove: org/user/membership creation, conflict
detection (409), Argon2id hashing of passwords, and audit recording scoped to the
new tenant from birth.
"""

from __future__ import annotations

import pytest

from marketpulse.application.services.audit import AuditService
from marketpulse.application.services.provisioning import TenantProvisioningService
from marketpulse.core.errors import AppError, ErrorCode
from marketpulse.core.security import verify_password
from marketpulse.domain.audit import AuditAction
from marketpulse.domain.tenancy import Role
from tests.fakes import (
    FakeClock,
    FakeMembershipRepository,
    FakeOrganizationRepository,
    FakeUserRepository,
    RecordingAuditWriter,
)


def _svc(fixed_now):
    orgs = FakeOrganizationRepository()
    users = FakeUserRepository()
    memberships = FakeMembershipRepository()
    audit = RecordingAuditWriter()
    svc = TenantProvisioningService(
        orgs, users, memberships, AuditService(audit), FakeClock(fixed_now)
    )
    return svc, orgs, users, memberships, audit


def _make_org(svc, slug="acme"):
    return svc.create_organization(
        slug=slug,
        display_name=slug.title(),
        default_market="US",
        timezone="UTC",
        base_currency="USD",
    )


def test_create_organization_persists_and_stamps_time(fixed_now) -> None:
    svc, orgs, *_ = _svc(fixed_now)
    org = _make_org(svc)
    assert orgs.get_by_slug("acme").id == org.id
    assert org.created_at == fixed_now


def test_create_organization_audits_under_new_tenant(fixed_now) -> None:
    svc, _, _, _, audit = _svc(fixed_now)
    org = _make_org(svc)
    assert len(audit.events) == 1
    assert audit.events[0]["action"] == AuditAction.ORGANIZATION_CREATED
    assert audit.events[0]["ctx"].organization_id == org.id


def test_create_organization_conflict_on_duplicate_slug(fixed_now) -> None:
    svc, *_ = _svc(fixed_now)
    _make_org(svc)
    with pytest.raises(AppError) as exc:
        _make_org(svc)
    assert exc.value.code == ErrorCode.CONFLICT
    assert exc.value.status_code == 409


def test_create_user_lowercases_email_and_hashes_password(fixed_now) -> None:
    svc, _, users, *_ = _svc(fixed_now)
    user = svc.create_user(email="Owner@Example.com", password="s3cret-pass")
    assert user.email == "owner@example.com"
    stored = users.hashes[user.id]
    assert stored != "s3cret-pass"
    assert verify_password(stored, "s3cret-pass") is True


def test_create_user_conflict_is_case_insensitive(fixed_now) -> None:
    svc, *_ = _svc(fixed_now)
    svc.create_user(email="a@x.com", password="p1")
    with pytest.raises(AppError) as exc:
        svc.create_user(email="A@X.com", password="p2")
    assert exc.value.code == ErrorCode.CONFLICT


def test_add_membership_persists_and_audits(fixed_now) -> None:
    svc, _, _, memberships, audit = _svc(fixed_now)
    org = _make_org(svc)
    user = svc.create_user(email="o@x.com", password="p")
    m = svc.add_membership(organization_id=org.id, user_id=user.id, role=Role.OWNER)
    assert m.organization_id == org.id
    assert m.role == Role.OWNER
    assert memberships.list_for_organization(org.id) == [m]
    assert any(e["action"] == AuditAction.MEMBERSHIP_ADDED for e in audit.events)
