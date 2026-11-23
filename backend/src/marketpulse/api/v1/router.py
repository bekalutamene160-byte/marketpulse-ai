"""Aggregates every v1 router under the /api/v1 prefix."""

from fastapi import APIRouter

from marketpulse.api.v1.routers import (
    audit_events,
    auth,
    health,
    members,
    organizations,
    workspaces,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(organizations.router)
api_router.include_router(members.router)
api_router.include_router(workspaces.router)
api_router.include_router(audit_events.router)
