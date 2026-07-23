from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from energy_agent.bootstrap.container import RepositoryContainer
from energy_agent.catalog.repository import CatalogRepository
from energy_agent.core.config import Settings
from energy_agent.indexing.repository import IndexRepository
from energy_agent.observability.tracing import Tracer
from energy_agent.persistence.repositories.alarm_dedup import AlarmDedupRepository
from energy_agent.persistence.repositories.audit import AuditRepository
from energy_agent.persistence.repositories.cases import CaseRepository
from energy_agent.persistence.repositories.diagnosis_review import DiagnosisReviewRepository
from energy_agent.persistence.repositories.diagnosis_run import (
    DiagnosisResultRepository,
    DiagnosisRunRepository,
)
from energy_agent.persistence.repositories.diagnosis_session import DiagnosisSessionRepository
from energy_agent.persistence.repositories.diagnosis_step_log import DiagnosisStepLogRepository
from energy_agent.timeline.repository import TimelineRepository


def build_repositories(
    sessions: async_sessionmaker[AsyncSession], settings: Settings, tracer: Tracer
) -> RepositoryContainer:
    indexes = IndexRepository(sessions, tracer)
    return RepositoryContainer(
        sessions=DiagnosisSessionRepository(sessions, tracer),
        steps=DiagnosisStepLogRepository(sessions, tracer),
        runs=DiagnosisRunRepository(sessions, tracer),
        results=DiagnosisResultRepository(sessions, tracer),
        audit=AuditRepository(sessions, tracer),
        alarm_dedup=AlarmDedupRepository(sessions, settings.alarm_dedup_window_seconds),
        indexes=indexes,
        cases=CaseRepository(sessions, indexes),
        reviews=DiagnosisReviewRepository(sessions),
        catalog=CatalogRepository(sessions),
        timeline=TimelineRepository(sessions),
    )
