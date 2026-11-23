"""Unit tests for the workspace use case: validation, persistence, audit, and the
org-scoping that the fake repository makes visible (RLS makes it real in prod).
"""

from __future__ import annotations

import uuid

import pytest

from marketpulse.application.services.audit import AuditService
from marketpulse.application.services.workspaces import WorkspaceService
from marketpulse.core.errors import AppError, ErrorCode
from marketpulse.core.tenancy import TenantContext
from marketpulse.domain.audit import AuditAction
from tests.fakes import FakeClock, FakeWorkspaceRepository, RecordingAuditWriter


def _ctx(org_id: uuid.UUID | None = None) -> TenantContext:
    return TenantContext(organization_id=org_id or uuid.uuid4())


def _svc(fixed_now):
    repo = FakeWorkspaceRepository()
    audit = RecordingAuditWriter()
    return WorkspaceService(repo, AuditService(audit), FakeClock(fixed_now)), repo, audit


def test_create_persists_and_audits_with_callers_tenant(fixed_now) -> None:
    svc, repo, audit = _svc(fixed_now)
    ctx = _ctx()
    ws = svc.create(ctx=ctx, name="Prod Catalog")
    assert ws.name == "Prod Catalog"
    assert ws.organization_id == ctx.organization_id
    assert ws.created_at == fixed_now
    assert repo.list_for_organization(ctx.organization_id) == [ws]
    assert len(audit.events) == 1
    assert audit.events[0]["action"] == AuditAction.WORKSPACE_CREATED
    assert audit.events[0]["entity_id"] == ws.id
    assert audit.events[0]["ctx"].organization_id == ctx.organization_id


def test_create_rejects_blank_name(fixed_now) -> None:
    svc, _, _ = _svc(fixed_now)
    with pytest.raises(AppError) as exc:
        svc.create(ctx=_ctx(), name="   ")
    assert exc.value.status_code == 422
    assert exc.value.code == ErrorCode.VALIDATION_ERROR


def test_create_rejects_name_over_100_chars(fixed_now) -> None:
    svc, _, _ = _svc(fixed_now)
    with pytest.raises(AppError) as exc:
        svc.create(ctx=_ctx(), name="x" * 101)
    assert exc.value.status_code == 422


def test_list_returns_only_the_current_tenant(fixed_now) -> None:
    svc, _, _ = _svc(fixed_now)
    a, b = _ctx(), _ctx()
    svc.create(ctx=a, name="A1")
    svc.create(ctx=b, name="B1")
    svc.create(ctx=a, name="A2")
    names = {w.name for w in svc.list_for_current(a)}
    assert names == {"A1", "A2"}
