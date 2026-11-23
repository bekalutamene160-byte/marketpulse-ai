"""Unit tests for the AuditService use case: it delegates to the writer port with the
explicit tenant context, never reading a hidden global for the tenant.
"""

from __future__ import annotations

import uuid

from marketpulse.application.services.audit import AuditService
from marketpulse.core.tenancy import TenantContext
from marketpulse.domain.audit import AuditAction
from tests.fakes import RecordingAuditWriter


def test_record_delegates_to_writer_with_the_callers_context() -> None:
    writer = RecordingAuditWriter()
    svc = AuditService(writer)
    ctx = TenantContext(organization_id=uuid.uuid4(), user_id=uuid.uuid4())
    entity_id = uuid.uuid4()
    svc.record(
        ctx=ctx,
        action=AuditAction.WORKSPACE_CREATED,
        entity_type="workspace",
        entity_id=entity_id,
        metadata={"name": "catalog"},
    )
    assert len(writer.events) == 1
    event = writer.events[0]
    assert event["ctx"] is ctx
    assert event["action"] == AuditAction.WORKSPACE_CREATED
    assert event["entity_id"] == entity_id
    assert event["metadata"] == {"name": "catalog"}


def test_record_defaults_metadata_to_an_empty_dict() -> None:
    writer = RecordingAuditWriter()
    AuditService(writer).record(
        ctx=TenantContext(organization_id=uuid.uuid4()),
        action=AuditAction.USER_CREATED,
        entity_type="user",
        entity_id=uuid.uuid4(),
    )
    assert writer.events[0]["metadata"] == {}
