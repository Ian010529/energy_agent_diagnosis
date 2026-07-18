from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from energy_agent.contracts.diagnosis import StepLogCreate, StepLogRecord
from energy_agent.core.errors import DependencyUnavailableError
from energy_agent.core.time import ensure_utc
from energy_agent.observability.redaction import safe_snapshot
from energy_agent.observability.tracing import Tracer
from energy_agent.persistence.models import DiagnosisStepLogModel


class DiagnosisStepLogRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        tracer: Tracer,
    ) -> None:
        self.session_factory = session_factory
        self.tracer = tracer

    @staticmethod
    def _record(model: DiagnosisStepLogModel) -> StepLogRecord:
        return StepLogRecord(
            id=model.id,
            session_id=model.session_id,
            run_id=model.run_id,
            trace_id=model.trace_id,
            step_name=model.step_name,
            step_status=model.step_status,
            input_snapshot=model.input_snapshot,
            output_snapshot=model.output_snapshot,
            error_code=model.error_code,
            started_at=ensure_utc(model.started_at),
            ended_at=ensure_utc(model.ended_at) if model.ended_at else None,
            duration_ms=model.duration_ms,
        )

    async def create(self, payload: StepLogCreate) -> StepLogRecord:
        with self.tracer.start_span(
            "persistence.diagnosis_step_log.create",
            trace_id=payload.trace_id,
            metadata={"session_id": payload.session_id, "step_name": payload.step_name},
        ):
            values = payload.model_dump(exclude={"input_snapshot", "output_snapshot"})
            model = DiagnosisStepLogModel(
                **values,
                input_snapshot=safe_snapshot(payload.input_snapshot),
                output_snapshot=safe_snapshot(payload.output_snapshot),
            )
            try:
                async with self.session_factory.begin() as session:
                    session.add(model)
                    await session.flush()
            except Exception as exc:
                raise DependencyUnavailableError("MySQL step log write failed") from exc
            return self._record(model)

    async def list_by_session(self, session_id: str, *, trace_id: str) -> list[StepLogRecord]:
        with self.tracer.start_span(
            "persistence.diagnosis_step_log.list",
            trace_id=trace_id,
            metadata={"session_id": session_id},
        ):
            try:
                async with self.session_factory() as session:
                    result = await session.execute(
                        select(DiagnosisStepLogModel)
                        .where(DiagnosisStepLogModel.session_id == session_id)
                        .order_by(DiagnosisStepLogModel.id)
                    )
                    models = result.scalars().all()
            except Exception as exc:
                raise DependencyUnavailableError("MySQL step log read failed") from exc
            return [self._record(model) for model in models]
