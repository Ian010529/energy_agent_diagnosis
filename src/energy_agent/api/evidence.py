from datetime import datetime

from fastapi import APIRouter, Request

from energy_agent.api.auth import actor_from_request, require_roles
from energy_agent.core.context import ActorRole
from energy_agent.evidence.contracts import EvidenceDetail, SessionTimeseriesResponse
from energy_agent.evidence.service import EvidenceService

router = APIRouter(prefix="/api/v1/diagnosis/sessions/{session_id}", tags=["evidence"])
READ_ROLES = {ActorRole.VIEWER, ActorRole.OPERATOR, ActorRole.REVIEWER, ActorRole.ADMIN}


def _authorize(request: Request) -> None:
    require_roles(actor_from_request(request), READ_ROLES)


@router.get("/evidence/{evidence_id}", response_model=EvidenceDetail)
async def evidence_detail(session_id: str, evidence_id: str, request: Request) -> EvidenceDetail:
    _authorize(request)
    return await EvidenceService.from_request(request).detail(session_id, evidence_id)


@router.get("/timeseries", response_model=SessionTimeseriesResponse)
async def timeseries(
    session_id: str,
    request: Request,
    run_id: str | None = None,
    metric: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> SessionTimeseriesResponse:
    _authorize(request)
    return await EvidenceService.from_request(request).timeseries(
        session_id, run_id, metric, start_time, end_time
    )
