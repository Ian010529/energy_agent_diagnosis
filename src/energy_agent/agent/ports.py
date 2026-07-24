from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel

from energy_agent.agent.events import DiagnosisEventEmitter
from energy_agent.agent.state import DiagnosisState
from energy_agent.contracts.diagnosis import (
    DiagnosisResultCreate,
    DiagnosisResultRecord,
    DiagnosisRunCreate,
    DiagnosisRunRecord,
    DiagnosisSessionCreate,
    DiagnosisSessionRecord,
    DiagnosisSessionUpdate,
    SessionMemoryPayload,
    StepLogCreate,
    StepLogRecord,
)
from energy_agent.core.context import ActorContext, ServiceActorContext
from energy_agent.reliability.contracts import AlarmDedupHit
from energy_agent.timeline.contracts import TimelineEventCreate
from energy_agent.tools.contracts import ToolResult

MemoryWriterPort = Callable[[DiagnosisState], Awaitable[None]]
ToolLogPort = Callable[[str, ToolResult, datetime, datetime], Awaitable[None]]
StepLogPort = Callable[
    [
        DiagnosisState,
        str,
        dict[str, object] | None,
        BaseException | None,
        datetime,
        datetime,
        int,
    ],
    Awaitable[None],
]


class DiagnosisSessionPort(Protocol):
    async def create(self, payload: DiagnosisSessionCreate) -> DiagnosisSessionRecord: ...

    async def get(self, session_id: str, *, trace_id: str) -> DiagnosisSessionRecord | None: ...

    async def update(
        self, session_id: str, payload: DiagnosisSessionUpdate, *, trace_id: str
    ) -> DiagnosisSessionRecord: ...


class DiagnosisRunPort(Protocol):
    async def create(
        self,
        payload: DiagnosisRunCreate,
        timeline_event: TimelineEventCreate | None = None,
    ) -> DiagnosisRunRecord: ...

    async def find_idempotent(
        self, session_id: str, key: str, *, trace_id: str
    ) -> DiagnosisRunRecord | None: ...

    async def find_idempotent_global(
        self, key: str, *, trace_id: str
    ) -> DiagnosisRunRecord | None: ...

    async def latest(self, session_id: str, *, trace_id: str) -> DiagnosisRunRecord | None: ...

    async def finish(self, run_id: str, phase: str, status: str) -> None: ...

    async def set_template(
        self,
        run_id: str,
        *,
        template_id: str | None,
        template_version: str | None,
        alarm_category: str | None,
    ) -> None: ...

    async def set_hardening_outcome(
        self,
        run_id: str,
        *,
        first_event_at: datetime | None,
        guardrail_status: str | None,
        failure_category: str | None = None,
    ) -> None: ...


class DiagnosisResultPort(Protocol):
    async def upsert(self, payload: DiagnosisResultCreate) -> DiagnosisResultRecord: ...

    async def latest(self, session_id: str) -> DiagnosisResultRecord | None: ...


class DiagnosisStepLogPort(Protocol):
    async def create(self, payload: StepLogCreate) -> StepLogRecord: ...

    async def list_by_session(self, session_id: str, *, trace_id: str) -> list[StepLogRecord]: ...


class AuditPort(Protocol):
    async def write(
        self,
        *,
        actor: ActorContext | ServiceActorContext,
        action: str,
        resource_type: str,
        resource_id: str,
        trace_id: str,
        outcome: str = "succeeded",
        session_id: str | None = None,
        case_id: str | None = None,
        snapshot: dict[str, Any] | None = None,
    ) -> None: ...


class AlarmDedupPort(Protocol):
    async def hit(
        self, device_id: str, alarm_category: str, alarm_id: str
    ) -> AlarmDedupHit | None: ...

    async def register(
        self,
        *,
        device_id: str,
        alarm_category: str,
        alarm_id: str,
        session_id: str,
    ) -> None: ...


class SessionMemoryPort(Protocol):
    async def save(self, payload: SessionMemoryPayload) -> None: ...

    async def get(self, session_id: str, *, trace_id: str) -> SessionMemoryPayload | None: ...


class ModelGenerationPort(Protocol):
    async def generate(
        self,
        *,
        trace_id: str,
        session_id: str,
        node_name: str,
        prompt_version: str,
        system_prompt: str,
        evidence_package: dict[str, object],
        output_schema: type[BaseModel],
    ) -> BaseModel | None: ...


class ToolExecutorPort(Protocol):
    @property
    def tool_names(self) -> frozenset[str]: ...

    async def execute(
        self, name: str, arguments: dict[str, object], trace_id: str
    ) -> ToolResult: ...


class DiagnosisGraphPort(Protocol):
    async def ainvoke(self, state: DiagnosisState) -> Any: ...


class DiagnosisRuntimeFactoryPort(Protocol):
    def create(
        self,
        *,
        tool_logger: ToolLogPort,
        memory_writer: MemoryWriterPort,
        step_logger: StepLogPort,
        emitter: DiagnosisEventEmitter,
    ) -> DiagnosisGraphPort: ...
