import json
from collections.abc import AsyncIterator

import anyio
from fastapi import APIRouter, Header, Request
from fastapi.responses import Response, StreamingResponse

from energy_agent.agent.events import QueueDiagnosisEventEmitter
from energy_agent.agent.service import DiagnosisService
from energy_agent.api.auth import actor_from_request, require_pilot_write, require_roles
from energy_agent.api.errors import error_response
from energy_agent.contracts.diagnosis import (
    CreateSessionRequest,
    CreateSessionResponse,
    DiagnosisChatRequest,
    DiagnosisResponse,
    SessionMessageRequest,
)
from energy_agent.contracts.events import SSEEvent
from energy_agent.core.context import ActorRole
from energy_agent.observability.metrics import RATE_LIMIT_REJECTIONS

router = APIRouter(prefix="/api/v1/diagnosis", tags=["diagnosis"])


@router.post("/sessions", response_model=CreateSessionResponse, status_code=201)
async def create_session(
    payload: CreateSessionRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> CreateSessionResponse:
    actor = actor_from_request(request)
    require_roles(actor, {ActorRole.OPERATOR, ActorRole.REVIEWER, ActorRole.ADMIN})
    require_pilot_write(request, actor)
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
    require_pilot_write(request, actor)
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
    require_pilot_write(request, actor)
    return await DiagnosisService.from_request(request).diagnose(
        DiagnosisChatRequest(session_id=session_id, **payload.model_dump()),
        idempotency_key,
        actor,
    )


def _sse(event: SSEEvent) -> str:
    data = event.model_dump(mode="json", exclude={"event"})
    return (
        f"event: {event.event.value}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
    )


@router.post("/sessions/{session_id}/messages/stream")
async def stream_message(
    session_id: str,
    payload: SessionMessageRequest,
    request: Request,
) -> Response:
    actor = actor_from_request(request)
    require_roles(actor, {ActorRole.OPERATOR, ActorRole.REVIEWER, ActorRole.ADMIN})
    require_pilot_write(request, actor)
    settings = request.app.state.settings
    stream_acquired = False
    if settings.rate_limit_enabled:
        try:
            stream_acquired = await request.app.state.rate_limiter.acquire_stream(
                actor.actor_id, settings.rate_limit_stream_concurrent
            )
        except Exception:
            if settings.pilot_mode:
                return error_response(
                    code="RATE_LIMIT_UNAVAILABLE",
                    message="Pilot streams are closed while rate limiting is unavailable",
                    status_code=503,
                    retryable=True,
                )
        if not stream_acquired:
            RATE_LIMIT_REJECTIONS.labels(group="stream").inc()
            response = error_response(
                code="RATE_LIMITED",
                message="Concurrent stream limit exceeded",
                status_code=429,
                retryable=True,
            )
            response.headers["Retry-After"] = "1"
            return response
    emitter = QueueDiagnosisEventEmitter()

    async def run_workflow() -> None:
        try:
            await DiagnosisService.from_request(request).diagnose(
                DiagnosisChatRequest(session_id=session_id, **payload.model_dump()),
                actor=actor,
                event_emitter=emitter,
            )
        finally:
            await emitter.close()

    async def events() -> AsyncIterator[str]:
        try:
            async with anyio.create_task_group() as task_group:
                task_group.start_soon(run_workflow)
                async for event in emitter.events():
                    if await request.is_disconnected():
                        task_group.cancel_scope.cancel()
                        return
                    yield _sse(event)
        finally:
            if settings.rate_limit_enabled and stream_acquired:
                await request.app.state.rate_limiter.release_stream(actor.actor_id)

    return StreamingResponse(events(), media_type="text/event-stream")


@router.get("/sessions/{session_id}", response_model=DiagnosisResponse)
async def get_session(session_id: str, request: Request) -> DiagnosisResponse:
    return await DiagnosisService.from_request(request).get_session(session_id)
