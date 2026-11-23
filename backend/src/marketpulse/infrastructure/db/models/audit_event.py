"""Audit event ORM model — tenant-scoped, append-only (blueprint 7.4, 16.3).

Row-level secured on ``organization_id``: a session sees only its own tenant's audit
trail. There is no UPDATE/DELETE path through the application (the writer only
inserts); retention is a future admin operation run from a privileged connection.
``metadata`` is JSONB and holds only safe, non-secret values (slugs, role names,
counts) — never credentials, full payloads, or PII.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from marketpulse.infrastructure.db.base import Base

if TYPE_CHECKING:
    from marketpulse.infrastructure.db.models.organization import OrganizationORM


class AuditEventORM(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, default="-")
    metadata_: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    # Many-to-one to the tenant root. The relationship — not just the ForeignKey — is
    # what orders the unit of work: SQLAlchemy only guarantees that a child row's
    # INSERT is emitted AFTER its parent's when a relationship() links the two
    # mappers; bare FK columns alone let audit_events flush before organizations
    # (regression caught by test_two_tenants_are_isolated). passive_deletes mirrors
    # ondelete=CASCADE: retention deletes happen in the database, not the ORM.
    organization: Mapped[OrganizationORM] = relationship("OrganizationORM", passive_deletes=True)
