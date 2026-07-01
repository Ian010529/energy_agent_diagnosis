"""阶段 4 本地诊断会话存储。

该实现只服务 Agent 主链路联调和回归测试；Redis 持久化属于阶段 5 范围。
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any

from energy_agent_diagnosis.contracts import (
    DiagnosisResult,
    DiagnosisSessionSnapshot,
    DiagnosisStateEvent,
    DiagnosisStatus,
    EvidencePackage,
    RequestContext,
    ToolCallSummary,
    utc_now,
)


@dataclass(slots=True)
class DiagnosisSessionRecord:
    """保存一次诊断会话的可恢复阶段 4 状态。"""

    request_context: RequestContext
    status: DiagnosisStatus = DiagnosisStatus.INIT
    events: list[DiagnosisStateEvent] = field(default_factory=list)
    tool_calls: list[ToolCallSummary] = field(default_factory=list)
    evidence_package: EvidencePackage | None = None
    result: DiagnosisResult | None = None
    clarification_answer: str | None = None
    created_at: Any = field(default_factory=utc_now)
    updated_at: Any = field(default_factory=utc_now)

    def snapshot(self) -> DiagnosisSessionSnapshot:
        """把内部可变记录转换为 API 使用的不可变快照模型。"""
        return DiagnosisSessionSnapshot(
            session_id=self.request_context.session_id,
            trace_id=self.request_context.trace_id,
            status=self.status,
            request_context=self.request_context,
            events=list(self.events),
            tool_calls=list(self.tool_calls),
            evidence_package=self.evidence_package,
            result=self.result,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class InMemoryDiagnosisSessionStore:
    """带基础并发保护的进程内会话表和幂等键索引。"""

    def __init__(self) -> None:
        """初始化空会话表；进程重启后数据会丢失。"""
        self._lock = asyncio.Lock()
        self._sessions: dict[str, DiagnosisSessionRecord] = {}
        self._idempotency: dict[str, str] = {}

    async def create(
        self,
        record: DiagnosisSessionRecord,
        *,
        idempotency_key: str | None = None,
    ) -> DiagnosisSessionSnapshot:
        """创建会话；相同幂等键重复提交时返回第一次创建的会话。"""
        async with self._lock:
            if idempotency_key and idempotency_key in self._idempotency:
                return self._sessions[self._idempotency[idempotency_key]].snapshot()
            session_id = record.request_context.session_id
            if session_id in self._sessions:
                raise ValueError("SESSION_ALREADY_EXISTS")
            self._sessions[session_id] = record
            if idempotency_key:
                self._idempotency[idempotency_key] = session_id
            return record.snapshot()

    async def get(self, session_id: str) -> DiagnosisSessionRecord:
        """返回内部记录；调用方必须通过 update 原子写回改动。"""
        async with self._lock:
            try:
                return self._sessions[session_id]
            except KeyError as exc:
                raise LookupError("SESSION_NOT_FOUND") from exc

    async def snapshot(self, session_id: str) -> DiagnosisSessionSnapshot:
        """读取会话快照。"""
        async with self._lock:
            try:
                return self._sessions[session_id].snapshot()
            except KeyError as exc:
                raise LookupError("SESSION_NOT_FOUND") from exc

    async def update(self, record: DiagnosisSessionRecord) -> DiagnosisSessionSnapshot:
        """原子替换会话记录并更新时间戳。"""
        async with self._lock:
            session_id = record.request_context.session_id
            if session_id not in self._sessions:
                raise LookupError("SESSION_NOT_FOUND")
            record.updated_at = utc_now()
            self._sessions[session_id] = record
            return record.snapshot()

    async def remember_idempotency(
        self,
        *,
        key: str | None,
        session_id: str,
    ) -> DiagnosisSessionSnapshot | None:
        """登记消息幂等键；重复键返回已有快照，首次登记返回 ``None``。"""
        if not key:
            return None
        async with self._lock:
            if key in self._idempotency:
                return self._sessions[self._idempotency[key]].snapshot()
            self._idempotency[key] = session_id
            return None
