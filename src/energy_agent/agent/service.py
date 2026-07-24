from energy_agent.agent.events import DiagnosisEventEmitter
from energy_agent.agent.execution_service import DiagnosisExecutionService
from energy_agent.agent.ports import (
    AlarmDedupPort,
    AuditPort,
    DiagnosisResultPort,
    DiagnosisRunPort,
    DiagnosisRuntimeFactoryPort,
    DiagnosisSessionPort,
    DiagnosisStepLogPort,
    SessionMemoryPort,
)
from energy_agent.agent.session_service import SessionService
from energy_agent.contracts.diagnosis import (
    CreateSessionRequest,
    CreateSessionResponse,
    DiagnosisChatRequest,
    DiagnosisResponse,
)
from energy_agent.core.context import ActorContext
from energy_agent.observability.tracing import Tracer
from energy_agent.timeline.ports import TimelineWriter


class DiagnosisService:
    """Stable API façade for session and execution application services."""

    def __init__(
        self,
        *,
        sessions: DiagnosisSessionPort,
        runs: DiagnosisRunPort,
        results: DiagnosisResultPort,
        step_logs: DiagnosisStepLogPort,
        memory: SessionMemoryPort,
        runtime_factory: DiagnosisRuntimeFactoryPort,
        tracer: Tracer,
        audit: AuditPort | None = None,
        alarm_dedup: AlarmDedupPort | None = None,
        timeline: TimelineWriter | None = None,
    ) -> None:
        execution = DiagnosisExecutionService(
            sessions=sessions,
            runs=runs,
            results=results,
            step_logs=step_logs,
            memory=memory,
            runtime_factory=runtime_factory,
            tracer=tracer,
            audit=audit,
            alarm_dedup=alarm_dedup,
            timeline=timeline,
        )
        self._execution = execution
        self._sessions = SessionService(execution)

    async def create_session(
        self,
        payload: CreateSessionRequest,
        idempotency_key: str | None,
        actor: ActorContext | None = None,
    ) -> CreateSessionResponse:
        return await self._sessions.create(payload, idempotency_key, actor)

    async def diagnose(
        self,
        payload: DiagnosisChatRequest,
        idempotency_key: str | None = None,
        actor: ActorContext | None = None,
        event_emitter: DiagnosisEventEmitter | None = None,
    ) -> DiagnosisResponse:
        return await self._execution.diagnose(payload, idempotency_key, actor, event_emitter)

    async def get_session(self, session_id: str) -> DiagnosisResponse:
        return await self._sessions.get(session_id)
