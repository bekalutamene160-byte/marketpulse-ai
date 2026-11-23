"""User ORM model — global identity (NOT tenant-scoped).

A user may belong to many organizations via ``memberships``. ``users`` itself carries
no ``organization_id``, so it is the one table in the tenant foundation that has no
row-level security policy: there is no single tenant to filter by. Access is mediated
through ``memberships`` (which IS row-level secured): to enumerate the members of an
organization you join through ``memberships``, and RLS hides every membership that is
not yours. Direct ``SELECT * FROM users`` is never exposed by a Phase 1 endpoint
(blueprint 14.1: the route list is a contract, not permission to expose every
operation). Phase 2 adds the auth flow that reads this table by email.

``password_hash`` is an Argon2id string. It is never selected into a domain ``User``
object (see domain/entities.py): the column is write-only from the application's
perspective until the Phase 2 credential check reads it by email.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from marketpulse.infrastructure.db.base import Base


class UserORM(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    # Email is the login identifier; stored lowercased and unique across the whole system.
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
