"""API tests for the tenant-foundation endpoints (Phase 1 exit gate: unauthorized
access returns correct errors; tenant context resolves from the request).

The app is built with the real HeaderTenantContextResolver (enabled in ``test``), so
the tenant-resolution and 401 paths run for real. The service dependencies are
overridden with fakes backed by in-memory repositories, so no database is needed:
the test proves the HTTP -> tenant-context -> use-case wiring and the error
envelope, while service logic is covered by the dedicated unit tests.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient

from marketpulse.api.deps import (
    get_audit_event_repository,
    get_organization_service,
    get_workspace_service,
)
from marketpulse.application.services.audit import AuditService
from marketpulse.application.services.organizations import OrganizationService
from marketpulse.application.services.workspaces import WorkspaceService
from marketpulse.domain.entities import AuditEvent
from tests.fakes import (
    FakeAuditEventRepository,
    FakeClock,
    FakeOrganizationRepository,
    FakeWorkspaceRepository,
    RecordingAuditWriter,
    make_organization,
)

ORG = uuid.uuid4()
USER = uuid.uuid4()


def _headers(org: uuid.UUID = ORG, user: uuid.UUID | None = USER) -> dict[str, str]:
    h: dict[str, str] = {"X-MP-Organization": str(org)}
    if user is not None:
        h["X-MP-User"] = str(user)
    return h


BuiltApp = tuple[Any, FakeWorkspaceRepository, RecordingAuditWriter, FakeAuditEventRepository]


def _build(make_tenant_app: Any, fixed_now: datetime) -> BuiltApp:
    app = make_tenant_app()
    org_repo = FakeOrganizationRepository()
    org_repo.add(make_organization(id=ORG, slug="acme"))
    ws_repo = FakeWorkspaceRepository()
    audit_writer = RecordingAuditWriter()
    audit_repo = FakeAuditEventRepository()
    app.dependency_overrides[get_organization_service] = lambda: OrganizationService(org_repo)
    app.dependency_overrides[get_workspace_service] = lambda: WorkspaceService(
        ws_repo, AuditService(audit_writer), FakeClock(fixed_now)
    )
    app.dependency_overrides[get_audit_event_repository] = lambda: audit_repo
    return app, ws_repo, audit_writer, audit_repo


def test_current_org_returns_401_without_tenant_context(make_tenant_app, fixed_now) -> None:
    app, *_ = _build(make_tenant_app, fixed_now)
    r = TestClient(app).get("/api/v1/organizations/current")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"
    assert r.headers["X-Request-ID"]


def test_current_org_returns_200_with_valid_context(make_tenant_app, fixed_now) -> None:
    app, *_ = _build(make_tenant_app, fixed_now)
    r = TestClient(app).get("/api/v1/organizations/current", headers=_headers())
    assert r.status_code == 200
    assert r.json()["id"] == str(ORG)
    assert r.json()["slug"] == "acme"


def test_current_org_returns_404_for_unknown_tenant(make_tenant_app, fixed_now) -> None:
    app, *_ = _build(make_tenant_app, fixed_now)
    r = TestClient(app).get("/api/v1/organizations/current", headers=_headers(org=uuid.uuid4()))
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_invalid_uuid_header_returns_401(make_tenant_app, fixed_now) -> None:
    app, *_ = _build(make_tenant_app, fixed_now)
    r = TestClient(app).get(
        "/api/v1/organizations/current", headers={"X-MP-Organization": "not-a-uuid"}
    )
    assert r.status_code == 401


def test_create_workspace_returns_201_and_audits(make_tenant_app, fixed_now) -> None:
    app, ws_repo, audit_writer, _ = _build(make_tenant_app, fixed_now)
    r = TestClient(app).post("/api/v1/workspaces", json={"name": "Catalog"}, headers=_headers())
    assert r.status_code == 201
    assert r.json()["name"] == "Catalog"
    assert r.json()["organization_id"] == str(ORG)
    assert len(ws_repo.list_for_organization(ORG)) == 1
    assert len(audit_writer.events) == 1


def test_create_workspace_requires_context(make_tenant_app, fixed_now) -> None:
    app, *_ = _build(make_tenant_app, fixed_now)
    r = TestClient(app).post("/api/v1/workspaces", json={"name": "x"})
    assert r.status_code == 401


def test_create_workspace_validates_name(make_tenant_app, fixed_now) -> None:
    app, *_ = _build(make_tenant_app, fixed_now)
    r = TestClient(app).post("/api/v1/workspaces", json={"name": ""}, headers=_headers())
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_list_workspaces_returns_only_the_current_tenant(make_tenant_app, fixed_now) -> None:
    app, *_ = _build(make_tenant_app, fixed_now)
    client = TestClient(app)
    client.post("/api/v1/workspaces", json={"name": "A"}, headers=_headers())
    client.post("/api/v1/workspaces", json={"name": "B"}, headers=_headers(org=uuid.uuid4()))
    r = client.get("/api/v1/workspaces", headers=_headers())
    assert r.status_code == 200
    assert {w["name"] for w in r.json()} == {"A"}


def test_audit_events_list_requires_context(make_tenant_app, fixed_now) -> None:
    app, *_ = _build(make_tenant_app, fixed_now)
    assert TestClient(app).get("/api/v1/audit-events").status_code == 401


def test_audit_events_list_returns_only_current_tenant(make_tenant_app, fixed_now) -> None:
    app, _, _, audit_repo = _build(make_tenant_app, fixed_now)
    other = uuid.uuid4()
    ours = _audit_event(ORG)
    theirs = _audit_event(other)
    audit_repo._rows.extend([ours, theirs])  # noqa: SLF001 - test injects rows
    r = TestClient(app).get("/api/v1/audit-events", headers=_headers())
    assert r.status_code == 200
    assert {e["organization_id"] for e in r.json()} == {str(ORG)}


def _audit_event(org_id: uuid.UUID) -> AuditEvent:
    return AuditEvent(
        id=uuid.uuid4(),
        organization_id=org_id,
        actor_user_id=None,
        action="workspace.created",
        entity_type="workspace",
        entity_id=uuid.uuid4(),
        occurred_at=datetime(2026, 11, 20, tzinfo=UTC),
        request_id="req-test",
        metadata={},
    )
