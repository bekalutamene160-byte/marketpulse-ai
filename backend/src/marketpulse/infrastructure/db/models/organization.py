"""Organization ORM model — the tenant root.

Every tenant-scoped row elsewhere carries ``organization_id`` pointing here. RLS is
enabled on this table in the initial migration with a policy that allows a session
to see only the row whose ``id`` equals ``current_setting('app.tenant_id')``
(ADR-0022). The application role does not own this table and has no BYPASSRLS.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from marketpulse.infrastructure.db.base import Base


class OrganizationORM(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    slug: Mapped[str] = mapped_column(String(63), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # ISO-3166 country/market code or a short market label; nullable until the owner sets it.
    default_market: Mapped[str | None] = mapped_column(String(63), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    # ISO-4217 currency code. Money is stored as NUMERIC; currency is a separate column (7.7).
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
