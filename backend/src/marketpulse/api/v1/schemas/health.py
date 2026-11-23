"""Response models for the health endpoints.

Public health output is intentionally coarse (blueprint 19.3): states and timings only.
No hostnames, no exception text, no configuration values.
"""

from typing import Literal

from pydantic import BaseModel


class LiveResponse(BaseModel):
    status: Literal["alive"]
    service: str
    version: str
    environment: str


class CheckResponse(BaseModel):
    status: Literal["ok", "failed", "not_configured"]
    required: bool
    latency_ms: float | None = None


class ReadyResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, CheckResponse]
