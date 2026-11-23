"""Membership ORM model — the user-to-organization link (tenant-scoped).

``memberships`` carries ``organization_id`` and is row-level secured: a session can
see only the memberships whose ``organization_id`` equals
``current_setting('app.tenant_id')``. This is what makes the global ``users`` table
safe to join through: an organization's member list is the join of its (RLS-filtered)
memberships with ``users``, so a tenant never sees another tenant's memberships.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from marketpulse.infrastructure.db.base import Base

if TYPE_CHECKING:
    from marketpulse.infrastructure.db.models.organization import OrganizationORM
    from marketpulse.infrastructure.db.models.user import UserORM


class MembershipORM(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        # A user has at most one membership row per organization.
        UniqueConstraint("organization_id", "user_id", name="uq_memberships_org_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    # Relationships (not just FK columns) are what orders cross-mapper flushes: the
    # unit of work emits memberships INSERTs only after their organization and user
    # rows exist. passive_deletes mirrors ondelete=CASCADE — the database cascades
    # deletes; the ORM never walks children.
    organization: Mapped[OrganizationORM] = relationship("OrganizationORM", passive_deletes=True)
    user: Mapped[UserORM] = relationship("UserORM", passive_deletes=True)
