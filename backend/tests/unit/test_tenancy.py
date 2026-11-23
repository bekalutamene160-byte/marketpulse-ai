"""Unit tests for tenant context: the value object, the dev header resolver, and the
context service that turns 'no context' into a 401 (blueprint Phase 1 exit gate).
"""

from __future__ import annotations

import uuid
from dataclasses import FrozenInstanceError

import pytest

from marketpulse.application.services.tenancy import TenantContextService
from marketpulse.core.errors import AppError, ErrorCode
from marketpulse.core.tenancy import TenantContext
from marketpulse.infrastructure.tenancy.header_resolver import HeaderTenantContextResolver

ORG = uuid.uuid4()
USER = uuid.uuid4()
WS = uuid.uuid4()


def test_tenant_context_defaults_optional_fields() -> None:
    ctx = TenantContext(organization_id=ORG)
    assert ctx.workspace_id is None
    assert ctx.user_id is None


def test_tenant_context_is_frozen() -> None:
    ctx = TenantContext(organization_id=ORG)
    with pytest.raises(FrozenInstanceError):
        ctx.organization_id = uuid.uuid4()  # type: ignore[misc]


def test_with_workspace_returns_new_context_preserving_org_and_user() -> None:
    ctx = TenantContext(organization_id=ORG, user_id=USER)
    ctx2 = ctx.with_workspace(WS)
    assert ctx2.workspace_id == WS
    assert ctx2.organization_id == ORG
    assert ctx2.user_id == USER
    assert ctx.workspace_id is None  # original unchanged


def test_header_resolver_returns_context_for_valid_uuid_headers() -> None:
    ctx = HeaderTenantContextResolver().resolve(
        {"X-MP-Organization": str(ORG), "X-MP-User": str(USER)}
    )
    assert ctx is not None
    assert ctx.organization_id == ORG
    assert ctx.user_id == USER


def test_header_resolver_accepts_lowercase_header_keys() -> None:
    ctx = HeaderTenantContextResolver().resolve({"x-mp-organization": str(ORG)})
    assert ctx is not None
    assert ctx.organization_id == ORG


def test_header_resolver_returns_none_when_org_header_missing() -> None:
    assert HeaderTenantContextResolver().resolve({}) is None


def test_header_resolver_returns_none_for_invalid_uuid() -> None:
    assert HeaderTenantContextResolver().resolve({"X-MP-Organization": "not-a-uuid"}) is None


def test_header_resolver_ignores_invalid_user_but_keeps_org() -> None:
    ctx = HeaderTenantContextResolver().resolve({"X-MP-Organization": str(ORG), "X-MP-User": "bad"})
    assert ctx is not None
    assert ctx.organization_id == ORG
    assert ctx.user_id is None


def test_header_resolver_includes_workspace_when_valid() -> None:
    ctx = HeaderTenantContextResolver().resolve(
        {"X-MP-Organization": str(ORG), "X-MP-Workspace": str(WS)}
    )
    assert ctx is not None
    assert ctx.workspace_id == WS


def test_context_service_raises_401_when_no_resolver_configured() -> None:
    svc = TenantContextService(None)
    with pytest.raises(AppError) as exc:
        svc.resolve({"X-MP-Organization": str(ORG)})
    assert exc.value.code == ErrorCode.UNAUTHORIZED
    assert exc.value.status_code == 401


def test_context_service_raises_401_when_resolver_returns_none() -> None:
    svc = TenantContextService(HeaderTenantContextResolver())
    with pytest.raises(AppError) as exc:
        svc.resolve({})
    assert exc.value.code == ErrorCode.UNAUTHORIZED
    assert exc.value.status_code == 401


def test_context_service_returns_context_when_resolved() -> None:
    svc = TenantContextService(HeaderTenantContextResolver())
    ctx = svc.resolve({"X-MP-Organization": str(ORG)})
    assert ctx.organization_id == ORG
