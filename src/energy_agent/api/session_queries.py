from datetime import datetime

from fastapi import APIRouter, Query, Request

from energy_agent.api.auth import actor_from_request, require_roles
from energy_agent.api.dependencies import CatalogServiceDependency, TimelineServiceDependency
from energy_agent.catalog.contracts import DiagnosisSessionListResponse
from energy_agent.core.context import ActorRole
from energy_agent.timeline.contracts import TimelineResponse

router = APIRouter(prefix="/api/v1/diagnosis/sessions", tags=["diagnosis-queries"])
READ_ROLES = {ActorRole.VIEWER, ActorRole.OPERATOR, ActorRole.REVIEWER, ActorRole.ADMIN}


def _authorize(request: Request) -> None:
    require_roles(actor_from_request(request), READ_ROLES)


@router.get("", response_model=DiagnosisSessionListResponse)
async def sessions(
    request: Request,
    service: CatalogServiceDependency,
    phase: str | None = None,
    source: str | None = None,
    site_id: str | None = None,
    device_id: str | None = None,
    alarm_id: str | None = None,
    created_by: str | None = None,
    latest_review_status: str | None = None,
    risk_level: str | None = None,
    from_time: datetime | None = None,
    to_time: datetime | None = None,
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
) -> DiagnosisSessionListResponse:
    _authorize(request)
    values = locals()
    names = (
        "phase",
        "source",
        "site_id",
        "device_id",
        "alarm_id",
        "created_by",
        "latest_review_status",
        "risk_level",
        "from_time",
        "to_time",
        "q",
    )
    filters = {name: values[name] for name in names if values[name] is not None}
    return await service.sessions(filters, limit, cursor)


@router.get("/{session_id}/timeline", response_model=TimelineResponse)
async def timeline(
    session_id: str,
    request: Request,
    service: TimelineServiceDependency,
) -> TimelineResponse:
    _authorize(request)
    return await service.get(session_id)
