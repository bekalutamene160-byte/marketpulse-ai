"""Unit tests for the organization read use case."""

from __future__ import annotations

import uuid

import pytest

from marketpulse.application.services.organizations import OrganizationService
from marketpulse.core.errors import AppError, ErrorCode
from marketpulse.core.tenancy import TenantContext
from tests.fakes import FakeOrganizationRepository, make_organization


def test_get_current_returns_the_tenant_organization() -> None:
    org = make_organization()
    repo = FakeOrganizationRepository()
    repo.add(org)
    svc = OrganizationService(repo)
    assert svc.get_current(TenantContext(organization_id=org.id)).id == org.id


def test_get_current_returns_404_when_not_visible(fixed_now) -> None:
    svc = OrganizationService(FakeOrganizationRepository())
    with pytest.raises(AppError) as exc:
        svc.get_current(TenantContext(organization_id=uuid.uuid4()))
    assert exc.value.code == ErrorCode.NOT_FOUND
    assert exc.value.status_code == 404
