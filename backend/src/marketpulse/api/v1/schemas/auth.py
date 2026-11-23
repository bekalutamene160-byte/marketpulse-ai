"""Request and response models for the authentication endpoints (Phase 2).

The same boundary rules as the Phase 1 schemas: Pydantic v2 models built from the
pure domain entities (``from_attributes=True``), so no ORM type is ever serialized.
Credentials never appear in any response — not the password, not the Argon2id hash,
not the session/CSRF token values (those travel ONLY in Set-Cookie headers).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from marketpulse.domain.entities import Membership, MemberSummary, Organization


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    # Length validated here AND in the service; the service owns the user-safe message.
    password: str = Field(min_length=12, max_length=128)
    organization_name: str = Field(min_length=1, max_length=200)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class SwitchOrganizationRequest(BaseModel):
    organization_id: uuid.UUID


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    created_at: datetime


class OrganizationBrief(BaseModel):
    """The org fields the shell needs (selector, header). Deliberately small."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    display_name: str
    is_demo: bool


class MembershipBrief(BaseModel):
    """One of the user's organizations, with the caller's role in it."""

    organization_id: uuid.UUID
    slug: str
    display_name: str
    role: str


class RegisterResponse(BaseModel):
    user: UserResponse
    organization: OrganizationBrief


class LoginResponse(BaseModel):
    user: UserResponse
    organization_id: uuid.UUID | None


class MeResponse(BaseModel):
    user: UserResponse
    active_organization: OrganizationBrief | None
    memberships: list[MembershipBrief]


class SwitchOrganizationResponse(BaseModel):
    organization: OrganizationBrief


class MemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    membership_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    role: str
    status: str
    created_at: datetime


def membership_briefs(
    memberships: list[Membership],
    orgs_by_id: dict[uuid.UUID, Organization],
) -> list[MembershipBrief]:
    """Join membership rows with their (RLS-visible) organizations for /auth/me."""
    briefs: list[MembershipBrief] = []
    for membership in memberships:
        org = orgs_by_id.get(membership.organization_id)
        if org is None:
            # RLS hid the organization (no membership row visible to the session):
            # skip rather than render a half-empty selector entry.
            continue
        briefs.append(
            MembershipBrief(
                organization_id=org.id,
                slug=org.slug,
                display_name=org.display_name,
                role=membership.role.value,
            )
        )
    return briefs


def member_responses(summaries: list[MemberSummary]) -> list[MemberResponse]:
    return [
        MemberResponse(
            membership_id=s.membership_id,
            user_id=s.user_id,
            email=s.email,
            role=s.role.value,
            status=s.status.value,
            created_at=s.created_at,
        )
        for s in summaries
    ]
