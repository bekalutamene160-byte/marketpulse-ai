"""Tenant context: the server-side identity under which a request or job runs.

This is the single source of truth for "which organization (and optionally which
workspace/user) does this operation act as?". It is ALWAYS resolved server-side
(blueprint 15.4): from an authenticated session in production (Phase 2), or from a
dev-only header in local/test (ADR-0024). A client may never supply an arbitrary
``organization_id`` directly to a repository, and worker jobs reload tenant metadata
from the database rather than trusting a message-supplied tenant id.

The value is a plain frozen dataclass with no framework imports, so the
application layer can depend on it without pulling in SQLAlchemy or Starlette
(blueprint 5.4 dependency direction).
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TenantContext:
    """The active tenant for the current request or background job.

    ``organization_id`` is always present (every tenant-scoped operation belongs
    to exactly one organization). ``workspace_id`` and ``user_id`` are optional:
    a system job has no user yet, and many operations are org-scoped rather than
    workspace-scoped.
    """

    organization_id: uuid.UUID
    workspace_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None

    def with_workspace(self, workspace_id: uuid.UUID) -> TenantContext:
        """Return a copy scoped to a specific workspace within this org."""
        return TenantContext(self.organization_id, workspace_id, self.user_id)


# A ContextVar lets code deep in the call stack (audit writers, repository
# helpers) read the active tenant without threading it through every signature.
# It is per-async-task, so concurrent requests never see each other's tenant. The
# API dependency and the worker task wrapper set it on entry and reset on exit.
tenant_context_var: ContextVar[TenantContext | None] = ContextVar("tenant_context", default=None)


class TenantContextError(RuntimeError):
    """Raised when tenant context is missing, inconsistent, or not allowed here."""
