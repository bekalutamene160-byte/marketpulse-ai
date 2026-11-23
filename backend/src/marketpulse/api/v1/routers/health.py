"""Health endpoints (blueprint 14.1 and 19.3).

GET /api/v1/health/live   process is up. Touches nothing external. Safe to poll often.
GET /api/v1/health/ready  required dependencies reachable. 200 when ready, 503 when not.
"""

from fastapi import APIRouter, Response

from marketpulse import __version__
from marketpulse.api.deps import ReadinessDep, SettingsDep
from marketpulse.api.v1.schemas.health import CheckResponse, LiveResponse, ReadyResponse

router = APIRouter(prefix="/health", tags=["system"])


@router.get("/live", response_model=LiveResponse)
async def live(settings: SettingsDep) -> LiveResponse:
    return LiveResponse(
        status="alive",
        service="marketpulse-api",
        version=__version__,
        environment=settings.environment,
    )


@router.get(
    "/ready",
    response_model=ReadyResponse,
    responses={503: {"model": ReadyResponse, "description": "A required dependency is down"}},
)
async def ready(service: ReadinessDep, response: Response) -> ReadyResponse:
    report = await service.check()
    if not report.ready:
        response.status_code = 503
    return ReadyResponse(
        status="ready" if report.ready else "not_ready",
        checks={
            c.name: CheckResponse(
                status=c.result.status, required=c.required, latency_ms=c.result.latency_ms
            )
            for c in report.checks
        },
    )
