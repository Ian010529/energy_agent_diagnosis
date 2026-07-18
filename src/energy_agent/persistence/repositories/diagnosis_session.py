from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from energy_agent.contracts.diagnosis import (
    DiagnosisSessionCreate,
    DiagnosisSessionRecord,
    DiagnosisSessionUpdate,
)
from energy_agent.core.errors import DependencyUnavailableError, ResourceNotFoundError
from energy_agent.core.time import ensure_utc, utc_now
from energy_agent.observability.tracing import Tracer
from energy_agent.persistence.models import DiagnosisSessionModel


class DiagnosisSessionRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        tracer: Tracer,
    ) -> None:
        self.session_factory = session_factory
        self.tracer = tracer

    @staticmethod
    def _record(model: DiagnosisSessionModel) -> DiagnosisSessionRecord:
        return DiagnosisSessionRecord(
            id=model.id,
            source=model.source,
            site_id=model.site_id,
            device_id=model.device_id,
            alarm_id=model.alarm_id,
            alarm_name=model.alarm_name,
            phase=model.phase,
            final_summary=model.final_summary,
            risk_level=model.risk_level,
            trace_id=model.trace_id,
            run_id=model.run_id,
            created_by=model.created_by,
            latest_review_status=model.latest_review_status,
            created_at=ensure_utc(model.created_at),
            updated_at=ensure_utc(model.updated_at),
        )

    async def create(self, payload: DiagnosisSessionCreate) -> DiagnosisSessionRecord:
        with self.tracer.start_span(
            "persistence.diagnosis_session.create",
            trace_id=payload.trace_id,
            metadata={"session_id": payload.id},
        ):
            now = utc_now()
            model = DiagnosisSessionModel(
                **payload.model_dump(mode="json"),
                created_at=now,
                updated_at=now,
            )
            try:
                async with self.session_factory.begin() as session:
                    session.add(model)
            except Exception as exc:
                raise DependencyUnavailableError("MySQL write failed") from exc
            return self._record(model)

    async def get(self, session_id: str, *, trace_id: str) -> DiagnosisSessionRecord | None:
        with self.tracer.start_span(
            "persistence.diagnosis_session.get",
            trace_id=trace_id,
            metadata={"session_id": session_id},
        ):
            try:
                async with self.session_factory() as session:
                    model = await session.get(DiagnosisSessionModel, session_id)
            except Exception as exc:
                raise DependencyUnavailableError("MySQL read failed") from exc
            return self._record(model) if model else None

    async def update(
        self,
        session_id: str,
        payload: DiagnosisSessionUpdate,
        *,
        trace_id: str,
    ) -> DiagnosisSessionRecord:
        with self.tracer.start_span(
            "persistence.diagnosis_session.update",
            trace_id=trace_id,
            metadata={"session_id": session_id},
        ):
            try:
                async with self.session_factory.begin() as session:
                    result = await session.execute(
                        select(DiagnosisSessionModel).where(DiagnosisSessionModel.id == session_id)
                    )
                    model = result.scalar_one_or_none()
                    if model is None:
                        raise ResourceNotFoundError(f"Diagnosis session {session_id} not found")
                    for key, value in payload.model_dump(exclude_unset=True, mode="json").items():
                        setattr(model, key, value)
                    model.updated_at = utc_now()
            except ResourceNotFoundError:
                raise
            except Exception as exc:
                raise DependencyUnavailableError("MySQL update failed") from exc
            return self._record(model)
