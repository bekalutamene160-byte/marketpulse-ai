"""Request and response models for the tenant-foundation endpoints (Phase 1).

These Pydantic v2 models are the public wire contract. They are built from the pure
domain entities (frozen dataclasses), so ``from_attributes=True`` lets Pydantic read
the entity fields directly. No ORM type is ever serialized to the client: the
boundary between the database row and the HTTP response is the domain entity.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    display_name: str
    default_market: str | None
    timezone: str
    base_currency: str
    is_demo: bool
    created_at: datetime
    updated_at: datetime


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    is_read_only: bool
    created_at: datetime
    updated_at: datetime


class CreateWorkspaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    is_read_only: bool = False


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    actor_user_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: uuid.UUID
    occurred_at: datetime
    request_id: str
    metadata: dict[str, Any]
