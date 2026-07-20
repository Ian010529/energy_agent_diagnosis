from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from energy_agent.contracts.diagnosis import (
    DiagnosisResultCreate,
    DiagnosisResultRecord,
    DiagnosisRunCreate,
    DiagnosisRunRecord,
)
from energy_agent.core.errors import DependencyUnavailableError
from energy_agent.core.time import ensure_utc, utc_now
from energy_agent.observability.tracing import Tracer
from energy_agent.persistence.models import DiagnosisResultModel, DiagnosisRunModel


class DiagnosisRunRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], tracer: Tracer) -> None:
        self.session_factory = session_factory
        self.tracer = tracer

    @staticmethod
    def _run(model: DiagnosisRunModel) -> DiagnosisRunRecord:
        return DiagnosisRunRecord(
            id=model.id,
            session_id=model.session_id,
            trace_id=model.trace_id,
            idempotency_key=model.idempotency_key,
            request_hash=model.request_hash,
            phase=model.phase,
            status=model.status,
            parent_run_id=model.parent_run_id,
            run_type=model.run_type,
            diagnosis_template_id=model.diagnosis_template_id,
            diagnosis_template_version=model.diagnosis_template_version,
            alarm_category=model.alarm_category,
            first_event_at=ensure_utc(model.first_event_at) if model.first_event_at else None,
            guardrail_status=model.guardrail_status,
            failure_category=model.failure_category,
            started_at=ensure_utc(model.started_at),
            ended_at=ensure_utc(model.ended_at) if model.ended_at else None,
            created_at=ensure_utc(model.created_at),
            updated_at=ensure_utc(model.updated_at),
        )

    async def create(self, payload: DiagnosisRunCreate) -> DiagnosisRunRecord:
        now = utc_now()
        model = DiagnosisRunModel(
            **payload.model_dump(mode="json"), started_at=now, created_at=now, updated_at=now
        )
        try:
            async with self.session_factory.begin() as session:
                session.add(model)
        except Exception as exc:
            raise DependencyUnavailableError("MySQL diagnosis run write failed") from exc
        return self._run(model)

    async def find_idempotent(
        self, session_id: str, key: str, *, trace_id: str
    ) -> DiagnosisRunRecord | None:
        try:
            async with self.session_factory() as session:
                result = await session.execute(
                    select(DiagnosisRunModel).where(
                        DiagnosisRunModel.session_id == session_id,
                        DiagnosisRunModel.idempotency_key == key,
                    )
                )
                model = result.scalar_one_or_none()
        except Exception as exc:
            raise DependencyUnavailableError("MySQL diagnosis run read failed") from exc
        return self._run(model) if model else None

    async def find_idempotent_global(self, key: str, *, trace_id: str) -> DiagnosisRunRecord | None:
        try:
            async with self.session_factory() as session:
                result = await session.execute(
                    select(DiagnosisRunModel)
                    .where(DiagnosisRunModel.idempotency_key == key)
                    .order_by(DiagnosisRunModel.created_at.desc())
                    .limit(1)
                )
                model = result.scalar_one_or_none()
        except Exception as exc:
            raise DependencyUnavailableError("MySQL diagnosis run read failed") from exc
        return self._run(model) if model else None

    async def latest(self, session_id: str, *, trace_id: str) -> DiagnosisRunRecord | None:
        try:
            async with self.session_factory() as session:
                result = await session.execute(
                    select(DiagnosisRunModel)
                    .where(DiagnosisRunModel.session_id == session_id)
                    .order_by(DiagnosisRunModel.created_at.desc())
                    .limit(1)
                )
                model = result.scalar_one_or_none()
        except Exception as exc:
            raise DependencyUnavailableError("MySQL diagnosis run read failed") from exc
        return self._run(model) if model else None

    async def finish(self, run_id: str, phase: str, status: str) -> None:
        try:
            async with self.session_factory.begin() as session:
                model = await session.get(DiagnosisRunModel, run_id)
                if model:
                    model.phase = phase
                    model.status = status
                    model.ended_at = utc_now()
                    model.updated_at = utc_now()
        except Exception as exc:
            raise DependencyUnavailableError("MySQL diagnosis run update failed") from exc

    async def set_template(
        self,
        run_id: str,
        *,
        template_id: str | None,
        template_version: str | None,
        alarm_category: str | None,
    ) -> None:
        try:
            async with self.session_factory.begin() as session:
                model = await session.get(DiagnosisRunModel, run_id)
                if model:
                    model.diagnosis_template_id = template_id
                    model.diagnosis_template_version = template_version
                    model.alarm_category = alarm_category
                    model.updated_at = utc_now()
        except Exception as exc:
            raise DependencyUnavailableError("MySQL diagnosis template update failed") from exc

    async def set_hardening_outcome(
        self,
        run_id: str,
        *,
        first_event_at: datetime | None,
        guardrail_status: str | None,
        failure_category: str | None = None,
    ) -> None:
        try:
            async with self.session_factory.begin() as session:
                model = await session.get(DiagnosisRunModel, run_id)
                if model:
                    model.first_event_at = first_event_at
                    model.guardrail_status = guardrail_status
                    model.failure_category = failure_category
                    model.updated_at = utc_now()
        except Exception as exc:
            raise DependencyUnavailableError("MySQL hardening outcome update failed") from exc


class DiagnosisResultRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], tracer: Tracer) -> None:
        self.session_factory = session_factory
        self.tracer = tracer

    @staticmethod
    def _record(model: DiagnosisResultModel) -> DiagnosisResultRecord:
        return DiagnosisResultRecord.model_validate(
            {
                "run_id": model.run_id,
                "session_id": model.session_id,
                "summary": model.summary,
                "candidate_causes": model.candidate_causes,
                "evidence": model.evidence,
                "inspection_steps": model.inspection_steps,
                "safety_notes": model.safety_notes,
                "missing_information": model.missing_information,
                "recommend_ticket": model.recommend_ticket,
                "risk_level": model.risk_level,
                "warnings": model.warnings,
                "degraded_components": model.degraded_components,
                "recommended_actions": model.recommended_actions,
                "guardrail_decision": model.guardrail_decision,
                "created_at": ensure_utc(model.created_at),
                "updated_at": ensure_utc(model.updated_at),
            }
        )

    async def upsert(self, payload: DiagnosisResultCreate) -> DiagnosisResultRecord:
        now = utc_now()
        values = payload.model_dump(mode="json")
        try:
            async with self.session_factory.begin() as session:
                model = await session.get(DiagnosisResultModel, payload.run_id)
                if model is None:
                    model = DiagnosisResultModel(**values, created_at=now, updated_at=now)
                    session.add(model)
                else:
                    for key, value in values.items():
                        setattr(model, key, value)
                    model.updated_at = now
        except Exception as exc:
            raise DependencyUnavailableError("MySQL diagnosis result write failed") from exc
        return self._record(model)

    async def latest(self, session_id: str) -> DiagnosisResultRecord | None:
        try:
            async with self.session_factory() as session:
                result = await session.execute(
                    select(DiagnosisResultModel)
                    .where(DiagnosisResultModel.session_id == session_id)
                    .order_by(DiagnosisResultModel.created_at.desc())
                    .limit(1)
                )
                model = result.scalar_one_or_none()
        except Exception as exc:
            raise DependencyUnavailableError("MySQL diagnosis result read failed") from exc
        return self._record(model) if model else None
