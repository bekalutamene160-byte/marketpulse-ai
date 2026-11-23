"""Workspace ORM model — a workspace within an organization (tenant-scoped).

Row-level secured on ``organization_id``. A session sees only the workspaces whose
``organization_id`` equals ``current_setting('app.tenant_id')``, and the ``WITH CHECK``
policy rejects an insert whose ``organization_id`` does not match, so a workspace can
never be created for another tenant even if a repository is misused (ADR-0022).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from marketpulse.infrastructure.db.base import Base

if TYPE_CHECKING:
    from marketpulse.infrastructure.db.models.organization import OrganizationORM


class WorkspaceORM(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_read_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    # Relationship (not just the FK column) is what orders cross-mapper flushes: the
    # unit of work emits workspace INSERTs only after their organization row exists.
    # passive_deletes mirrors ondelete=CASCADE — the database cascades deletes.
    organization: Mapped[OrganizationORM] = relationship("OrganizationORM", passive_deletes=True)
