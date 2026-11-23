"""Audit action vocabulary (blueprint 7.4 ``audit_events``, 16.3 structured logs).

An audit row records WHO did WHAT to WHICH entity, WHEN, under which request and
trace. Actions are a closed enum so retention queries and dashboards filter
reliably. Add a new action only in the same change that produces it, with a test.
"""

from __future__ import annotations

from enum import StrEnum


class AuditAction(StrEnum):
    ORGANIZATION_CREATED = "organization.created"
    WORKSPACE_CREATED = "workspace.created"
    MEMBERSHIP_ADDED = "membership.added"
    MEMBERSHIP_REMOVED = "membership.removed"
    MEMBERSHIP_ROLE_CHANGED = "membership.role_changed"
    USER_CREATED = "user.created"
    USER_DISABLED = "user.disabled"
    USER_REENABLED = "user.reenabled"
