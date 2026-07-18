from fastapi import APIRouter, Header, Query, Request

from energy_agent.api.auth import actor_from_request, require_roles
from energy_agent.cases.service import CaseService
from energy_agent.contracts.cases import (
    CaseDisableRequest,
    CaseListResponse,
    CasePatchRequest,
    CaseReviewEvent,
    CaseReviewRequest,
    CaseRevisionRequest,
    DiagnosisCase,
    DiagnosisReviewRequest,
    DiagnosisReviewResponse,
)
from energy_agent.core.context import ActorRole

router = APIRouter(tags=["cases"])


@router.post(
    "/api/v1/diagnosis/sessions/{session_id}/review",
    response_model=DiagnosisReviewResponse,
)
async def review_diagnosis(
    session_id: str,
    payload: DiagnosisReviewRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> DiagnosisReviewResponse:
    actor = actor_from_request(request, explicit=True)
    require_roles(actor, {ActorRole.OPERATOR, ActorRole.REVIEWER, ActorRole.ADMIN})
    return await CaseService.from_request(request).review_diagnosis(
        session_id, payload, actor, idempotency_key
    )


@router.get("/api/v1/cases", response_model=CaseListResponse)
async def list_cases(
    request: Request,
    review_status: str | None = None,
    device_type: str | None = None,
    device_model: str | None = None,
    alarm_name: str | None = None,
    created_by: str | None = None,
    is_active: bool | None = Query(default=None),
) -> CaseListResponse:
    actor_from_request(request)
    items = await CaseService.from_request(request).list_cases(
        {
            key: value
            for key, value in locals().items()
            if key
            in {
                "review_status",
                "device_type",
                "device_model",
                "alarm_name",
                "created_by",
                "is_active",
            }
            and value is not None
        }
    )
    return CaseListResponse(items=items, total=len(items))


@router.get("/api/v1/cases/{case_id}", response_model=DiagnosisCase)
async def get_case(case_id: str, request: Request) -> DiagnosisCase:
    actor_from_request(request)
    return await CaseService.from_request(request).get(case_id)


@router.get("/api/v1/cases/{case_id}/history", response_model=list[CaseReviewEvent])
async def case_history(case_id: str, request: Request) -> list[CaseReviewEvent]:
    actor_from_request(request)
    return await CaseService.from_request(request).history(case_id)


@router.patch("/api/v1/cases/{case_id}", response_model=DiagnosisCase)
async def patch_case(case_id: str, payload: CasePatchRequest, request: Request) -> DiagnosisCase:
    actor = actor_from_request(request, explicit=True)
    require_roles(actor, {ActorRole.OPERATOR, ActorRole.REVIEWER, ActorRole.ADMIN})
    return await CaseService.from_request(request).patch(case_id, payload, actor)


@router.post("/api/v1/cases/{case_id}/submit", response_model=DiagnosisCase)
async def submit_case(
    case_id: str,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> DiagnosisCase:
    actor = actor_from_request(request, explicit=True)
    require_roles(actor, {ActorRole.OPERATOR, ActorRole.REVIEWER, ActorRole.ADMIN})
    return await CaseService.from_request(request).submit(case_id, actor, idempotency_key)


@router.post("/api/v1/cases/{case_id}/review", response_model=DiagnosisCase)
async def review_case(
    case_id: str,
    payload: CaseReviewRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> DiagnosisCase:
    actor = actor_from_request(request, explicit=True)
    require_roles(actor, {ActorRole.REVIEWER, ActorRole.ADMIN})
    return await CaseService.from_request(request).review_case(
        case_id, payload, actor, idempotency_key
    )


@router.post("/api/v1/cases/{case_id}/disable", response_model=DiagnosisCase)
async def disable_case(
    case_id: str,
    payload: CaseDisableRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> DiagnosisCase:
    actor = actor_from_request(request, explicit=True)
    require_roles(actor, {ActorRole.REVIEWER, ActorRole.ADMIN})
    return await CaseService.from_request(request).disable(case_id, payload, actor, idempotency_key)


@router.post("/api/v1/cases/{case_id}/revisions", response_model=DiagnosisCase)
async def revise_case(
    case_id: str,
    payload: CaseRevisionRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> DiagnosisCase:
    actor = actor_from_request(request, explicit=True)
    require_roles(actor, {ActorRole.OPERATOR, ActorRole.REVIEWER, ActorRole.ADMIN})
    return await CaseService.from_request(request).revision(
        case_id, payload, actor, idempotency_key
    )


@router.post("/api/v1/cases/{case_id}/reindex", response_model=DiagnosisCase)
async def reindex_case(
    case_id: str,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> DiagnosisCase:
    actor = actor_from_request(request, explicit=True)
    require_roles(actor, {ActorRole.REVIEWER, ActorRole.ADMIN})
    return await CaseService.from_request(request).reindex(case_id, actor, idempotency_key)
