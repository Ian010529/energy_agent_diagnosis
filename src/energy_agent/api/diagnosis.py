import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Header, Request
from fastapi.responses import StreamingResponse

from energy_agent.agent.service import DiagnosisService
from energy_agent.api.auth import actor_from_request, require_roles
from energy_agent.contracts.diagnosis import (
    CreateSessionRequest,
    CreateSessionResponse,
    DiagnosisChatRequest,
    DiagnosisResponse,
    SessionMessageRequest,
)
from energy_agent.contracts.events import SSEEventType
from energy_agent.core.context import ActorRole

router = APIRouter(prefix="/api/v1/diagnosis", tags=["diagnosis"])


@router.post("/sessions", response_model=CreateSessionResponse, status_code=201)
async def create_session(
    payload: CreateSessionRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> CreateSessionResponse:
    actor = actor_from_request(request)
    require_roles(actor, {ActorRole.OPERATOR, ActorRole.REVIEWER, ActorRole.ADMIN})
    return await DiagnosisService.from_request(request).create_session(
        payload, idempotency_key, actor
    )


@router.post("/chat", response_model=DiagnosisResponse)
async def chat(
    payload: DiagnosisChatRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> DiagnosisResponse:
    actor = actor_from_request(request)
    require_roles(actor, {ActorRole.OPERATOR, ActorRole.REVIEWER, ActorRole.ADMIN})
    return await DiagnosisService.from_request(request).diagnose(payload, idempotency_key, actor)


@router.post("/sessions/{session_id}/messages", response_model=DiagnosisResponse)
async def session_message(
    session_id: str,
    payload: SessionMessageRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> DiagnosisResponse:
    actor = actor_from_request(request)
    require_roles(actor, {ActorRole.OPERATOR, ActorRole.REVIEWER, ActorRole.ADMIN})
    return await DiagnosisService.from_request(request).diagnose(
        DiagnosisChatRequest(session_id=session_id, **payload.model_dump()),
        idempotency_key,
        actor,
    )


def _sse(event: SSEEventType, data: dict[str, object]) -> str:
    return f"event: {event.value}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post("/sessions/{session_id}/messages/stream")
async def stream_message(
    session_id: str,
    payload: SessionMessageRequest,
    request: Request,
) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        actor = actor_from_request(request)
        require_roles(actor, {ActorRole.OPERATOR, ActorRole.REVIEWER, ActorRole.ADMIN})
        yield _sse(SSEEventType.INTENT_IDENTIFIED, {"session_id": session_id})
        yield _sse(SSEEventType.DATA_FETCH_STARTED, {"session_id": session_id})
        result = await DiagnosisService.from_request(request).diagnose(
            DiagnosisChatRequest(session_id=session_id, **payload.model_dump()),
            actor=actor,
        )
        yield _sse(
            SSEEventType.RETRIEVAL_COMPLETED,
            {"session_id": session_id, "evidence_refs": result.evidence_refs},
        )
        if result.phase.value == "NEED_USER_INPUT":
            yield _sse(
                SSEEventType.NEED_USER_INPUT,
                {
                    "session_id": session_id,
                    "questions": [
                        item.model_dump(mode="json") for item in result.clarification_questions
                    ],
                },
            )
            return
        yield _sse(
            SSEEventType.DRAFT_GENERATED,
            {"session_id": session_id, "run_id": result.run_id},
        )
        yield _sse(
            SSEEventType.COMPLETED,
            result.model_dump(mode="json"),
        )

    return StreamingResponse(events(), media_type="text/event-stream")


@router.get("/sessions/{session_id}", response_model=DiagnosisResponse)
async def get_session(session_id: str, request: Request) -> DiagnosisResponse:
    return await DiagnosisService.from_request(request).get_session(session_id)
