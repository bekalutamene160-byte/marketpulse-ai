"""ORM models for the tenant foundation and authentication.

Importing this package imports every model module, registering them on ``Base`` so
that ``Base.metadata`` reflects the full schema for Alembic autogenerate and for the
offline DDL-compilation test. Keep this list in sync with the migrations.
"""

from __future__ import annotations

from marketpulse.infrastructure.db.models.audit_event import AuditEventORM
from marketpulse.infrastructure.db.models.auth_session import AuthSessionORM
from marketpulse.infrastructure.db.models.membership import MembershipORM
from marketpulse.infrastructure.db.models.organization import OrganizationORM
from marketpulse.infrastructure.db.models.user import UserORM
from marketpulse.infrastructure.db.models.workspace import WorkspaceORM

__all__ = [
    "AuditEventORM",
    "AuthSessionORM",
    "MembershipORM",
    "OrganizationORM",
    "UserORM",
    "WorkspaceORM",
]
