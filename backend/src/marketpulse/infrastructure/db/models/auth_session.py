"""Auth session ORM model — server-side login sessions (Phase 2, blueprint 15.1).

A session belongs to a USER, not to a tenant: like ``users`` it is global identity
state and carries no row-level security. The cookie token and the CSRF token are
stored ONLY as SHA-256 digests, so a database leak cannot be replayed as a login.
``organization_id`` is the user's ACTIVE organization (workspace selector) and
cascades: deleting an organization ends its sessions instead of leaving one pointing
at a dead tenant.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from marketpulse.infrastructure.db.base import Base

if TYPE_CHECKING:
    from marketpulse.infrastructure.db.models.organization import OrganizationORM
    from marketpulse.infrastructure.db.models.user import UserORM


class AuthSessionORM(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # SHA-256 hex of the opaque session token; unique so a token maps to one row.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # SHA-256 hex of the CSRF token bound to this session (double-submit check).
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(nullable=False)

    # Relationships (not just FK columns) order cross-mapper flushes — the Phase 1
    # hotfix lesson. passive_deletes mirrors ondelete=CASCADE.
    user: Mapped[UserORM] = relationship("UserORM", passive_deletes=True)
    organization: Mapped[OrganizationORM | None] = relationship(
        "OrganizationORM", passive_deletes=True
    )
