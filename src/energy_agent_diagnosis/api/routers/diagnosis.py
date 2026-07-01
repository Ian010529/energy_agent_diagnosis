"""阶段 4 诊断会话 API 与 SSE 进度接口。"""

import json
from collections.abc import AsyncIterator, Awaitable
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse

from energy_agent_diagnosis.agent import DiagnosisAgentService
from energy_agent_diagnosis.api.dependencies import require_roles
from energy_agent_diagnosis.contracts import (
    DiagnosisMessageCreate,
    DiagnosisSessionCreate,
    DiagnosisSessionSnapshot,
    Principal,
    Role,
)
from energy_agent_diagnosis.core.errors import AppError
from energy_agent_diagnosis.core.trace import get_trace_id

router = APIRouter(prefix="/api/v1/diagnosis", tags=["diagnosis"])


def _agent_service(request: Request) -> DiagnosisAgentService:
    """从应用状态读取阶段 4 Agent 服务。"""
    return cast(DiagnosisAgentService, request.app.state.agent_service)


def _primary_role(principal: Principal) -> Role:
    """为诊断上下文选择一个稳定角色。"""
    for role in (Role.OPERATOR, Role.REVIEWER, Role.ADMIN, Role.VIEWER):
        if role in principal.roles:
            return role
    return Role.VIEWER


async def _safe_service_call[T](call: Awaitable[T]) -> T:
    """把逻辑层会话异常转换为标准 HTTP 错误。"""
    try:
        return await call
    except LookupError as exc:
        raise AppError(
            status_code=404,
            error_code="SESSION_NOT_FOUND",
            message="诊断会话不存在",
        ) from exc
    except ValueError as exc:
        if str(exc) == "SESSION_ALREADY_EXISTS":
            raise AppError(
                status_code=409,
                error_code="SESSION_ALREADY_EXISTS",
                message="诊断会话已存在",
            ) from exc
        raise


@router.post("/sessions")
async def create_session(
    payload: DiagnosisSessionCreate,
    request: Request,
    principal: Annotated[Principal, Depends(require_roles(Role.OPERATOR, Role.ADMIN))],
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
) -> DiagnosisSessionSnapshot:
    """创建诊断会话。"""
    return await _safe_service_call(
        _agent_service(request).create_session(
            payload,
            trace_id=get_trace_id(),
            user_id=principal.user_id,
            role=_primary_role(principal),
            idempotency_key=x_idempotency_key,
        )
    )


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: str,
    payload: DiagnosisMessageCreate,
    request: Request,
    principal: Annotated[Principal, Depends(require_roles(Role.OPERATOR, Role.ADMIN))],
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
) -> DiagnosisSessionSnapshot:
    """向会话发送消息并执行或恢复诊断流程。"""
    _ = principal
    return await _safe_service_call(
        _agent_service(request).send_message(
            session_id,
            payload,
            trace_id=get_trace_id(),
            idempotency_key=x_idempotency_key,
        )
    )


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    request: Request,
    principal: Annotated[
        Principal,
        Depends(require_roles(Role.VIEWER, Role.OPERATOR, Role.REVIEWER, Role.ADMIN)),
    ],
) -> DiagnosisSessionSnapshot:
    """查询诊断会话状态、证据包和结果。"""
    _ = principal
    return await _safe_service_call(_agent_service(request).get_session(session_id))


@router.post("/chat")
async def chat(
    payload: DiagnosisSessionCreate,
    request: Request,
    principal: Annotated[Principal, Depends(require_roles(Role.OPERATOR, Role.ADMIN))],
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
) -> DiagnosisSessionSnapshot:
    """便捷诊断入口：创建会话并立即执行首轮诊断。"""
    return await _safe_service_call(
        _agent_service(request).chat(
            payload,
            trace_id=get_trace_id(),
            user_id=principal.user_id,
            role=_primary_role(principal),
            idempotency_key=x_idempotency_key,
        )
    )


@router.get("/sessions/{session_id}/events")
async def stream_events(
    session_id: str,
    request: Request,
    principal: Annotated[
        Principal,
        Depends(require_roles(Role.VIEWER, Role.OPERATOR, Role.REVIEWER, Role.ADMIN)),
    ],
) -> StreamingResponse:
    """以 SSE 格式输出诊断进度事件。"""
    _ = principal
    snapshot = await _safe_service_call(_agent_service(request).get_session(session_id))

    async def event_stream() -> AsyncIterator[str]:
        """逐条输出已记录的诊断事件，客户端断连时立即停止。"""
        for event in snapshot.events:
            if await request.is_disconnected():
                break
            data = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
            yield f"event: {event.event}\ndata: {data}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
