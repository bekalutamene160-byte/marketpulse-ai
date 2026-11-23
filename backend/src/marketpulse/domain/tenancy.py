"""Tenant domain vocabulary: roles, membership and user states.

Pure Python only (blueprint 5.4: ``domain`` imports no frameworks and no SDKs).
These types are the shared language between application use cases and the
persistence layer. Adding a value here requires a producer and a test, so the
enum stays closed and dashboards can filter reliably.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    """Membership role within an organization (blueprint 15.1 RBAC)."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class MembershipStatus(StrEnum):
    """Lifecycle state of a user-to-organization link."""

    ACTIVE = "active"
    INVITED = "invited"
    SUSPENDED = "suspended"


class UserStatus(StrEnum):
    """Account state. A disabled user cannot authenticate even with a valid hash."""

    ACTIVE = "active"
    DISABLED = "disabled"
