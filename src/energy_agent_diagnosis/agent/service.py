"""阶段 4 Agent 服务层，连接 API、会话存储和 LangGraph 工作流。"""

from typing import Any

from energy_agent_diagnosis.agent.workflow import DiagnosisWorkflow
from energy_agent_diagnosis.contracts import (
    AlarmContext,
    DiagnosisMessageCreate,
    DiagnosisSessionCreate,
    DiagnosisSessionSnapshot,
    RequestContext,
    Role,
    new_session_id,
)
from energy_agent_diagnosis.memory import DiagnosisSessionRecord, InMemoryDiagnosisSessionStore
from energy_agent_diagnosis.ports.providers import ProviderLookup


class DiagnosisAgentService:
    """提供阶段 4 诊断会话和消息处理入口。"""

    def __init__(
        self,
        *,
        registry: ProviderLookup,
        settings: Any,
        store: InMemoryDiagnosisSessionStore,
    ) -> None:
        """绑定单进程内共享依赖。"""
        self._store = store
        self._workflow = DiagnosisWorkflow(registry=registry, settings=settings)

    async def create_session(
        self,
        payload: DiagnosisSessionCreate,
        *,
        trace_id: str,
        user_id: str,
        role: Role,
        idempotency_key: str | None = None,
    ) -> DiagnosisSessionSnapshot:
        """创建诊断会话但不自动执行，便于前端先建立会话再订阅 SSE。"""
        request_context = RequestContext(
            request_id=payload.request_id or f"req-{trace_id}",
            trace_id=trace_id,
            session_id=payload.session_id or new_session_id(),
            request_source=payload.source,
            user_id=user_id,
            role=role,
            device_id=payload.device_id,
            alarm=AlarmContext(alarm_id=payload.alarm_id) if payload.alarm_id else None,
            message=payload.message,
            stream=payload.stream,
            debug=payload.debug,
        )
        return await self._store.create(
            DiagnosisSessionRecord(request_context=request_context),
            idempotency_key=idempotency_key,
        )

    async def send_message(
        self,
        session_id: str,
        payload: DiagnosisMessageCreate,
        *,
        trace_id: str,
        idempotency_key: str | None = None,
    ) -> DiagnosisSessionSnapshot:
        """追加用户消息并执行或恢复 LangGraph 诊断流程。"""
        existing = await self._store.remember_idempotency(
            key=idempotency_key,
            session_id=session_id,
        )
        if existing is not None:
            return existing

        record = await self._store.get(session_id)
        request_context = record.request_context.model_copy(
            update={
                "trace_id": trace_id,
                "request_id": payload.request_id or f"req-{trace_id}",
                "message": payload.message,
                "device_id": payload.device_id or record.request_context.device_id,
                "alarm": AlarmContext(alarm_id=payload.alarm_id)
                if payload.alarm_id
                else record.request_context.alarm,
                "stream": payload.stream,
                "debug": payload.debug,
            }
        )
        clarification_answer = payload.message if record.status.value == "NEED_USER_INPUT" else None
        state = await self._workflow.run(
            request_context=request_context,
            existing_events=record.events,
            existing_tool_calls=record.tool_calls,
            clarification_answer=clarification_answer,
        )
        record.request_context = state["request_context"]
        record.status = state["status"]
        record.events = state["events"]
        record.tool_calls = state["tool_calls"]
        record.evidence_package = state.get("evidence_package")
        record.result = state.get("result")
        record.clarification_answer = clarification_answer
        return await self._store.update(record)

    async def chat(
        self,
        payload: DiagnosisSessionCreate,
        *,
        trace_id: str,
        user_id: str,
        role: Role,
        idempotency_key: str | None = None,
    ) -> DiagnosisSessionSnapshot:
        """便捷入口：创建会话后立即执行首轮诊断。"""
        created = await self.create_session(
            payload,
            trace_id=trace_id,
            user_id=user_id,
            role=role,
            idempotency_key=idempotency_key,
        )
        return await self.send_message(
            created.session_id,
            DiagnosisMessageCreate(
                request_id=payload.request_id,
                message=payload.message,
                alarm_id=payload.alarm_id,
                device_id=payload.device_id,
                stream=payload.stream,
                debug=payload.debug,
            ),
            trace_id=trace_id,
        )

    async def get_session(self, session_id: str) -> DiagnosisSessionSnapshot:
        """读取诊断会话快照。"""
        return await self._store.snapshot(session_id)
