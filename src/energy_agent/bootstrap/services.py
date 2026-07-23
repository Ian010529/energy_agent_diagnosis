from energy_agent.agent.service import DiagnosisService
from energy_agent.bootstrap.container import (
    ProviderContainer,
    RepositoryContainer,
    ServiceContainer,
)
from energy_agent.cases.service import CaseService
from energy_agent.catalog.service import CatalogService
from energy_agent.core.config import Settings
from energy_agent.evidence.repository import MySQLEvidenceRepository
from energy_agent.evidence.service import EvidenceService
from energy_agent.memory.session_store import RedisSessionStore
from energy_agent.observability.tracing import Tracer
from energy_agent.persistence.repositories.review_recorder import (
    RepositoryDiagnosisReviewRecorder,
)
from energy_agent.reliability.registry import CircuitBreakerRegistry
from energy_agent.retrieval.service import RetrievalService
from energy_agent.timeline.service import TimelineService
from energy_agent.tools.registry import ToolRegistry


def build_services(
    *,
    settings: Settings,
    repositories: RepositoryContainer,
    providers: ProviderContainer,
    retrieval: RetrievalService,
    tools: ToolRegistry,
    memory: RedisSessionStore,
    tracer: Tracer,
    circuit_breakers: CircuitBreakerRegistry,
) -> ServiceContainer:
    review_recorder = RepositoryDiagnosisReviewRecorder(repositories.reviews)
    timeline = TimelineService(
        repositories.timeline,
        repositories.sessions,
        repositories.steps,
        repositories.results,
        repositories.reviews,
        repositories.cases,
    )
    return ServiceContainer(
        diagnosis=DiagnosisService(
            sessions=repositories.sessions,
            runs=repositories.runs,
            results=repositories.results,
            step_logs=repositories.steps,
            memory=memory,
            tools=tools,
            tracer=tracer,
            model_gateway=providers.model,
            audit=repositories.audit,
            alarm_dedup=repositories.alarm_dedup,
            circuit_breakers=circuit_breakers,
            timeline=timeline,
        ),
        cases=CaseService(
            cases=repositories.cases,
            sessions=repositories.sessions,
            results=repositories.results,
            audit=repositories.audit,
            review_recorder=review_recorder,
            tracer=tracer,
            embedding=providers.embedding,
            milvus=providers.vector_search,
            index_execution_mode=settings.index_execution_mode,
            index_max_attempts=settings.index_max_attempts,
            timeline=timeline,
        ),
        catalog=CatalogService(repositories.catalog, settings),
        timeline=timeline,
        evidence=EvidenceService(
            sessions=repositories.sessions,
            results=repositories.results,
            runs=repositories.runs,
            memory=memory,
            sources=MySQLEvidenceRepository(providers.mysql_sessions),
            catalog=repositories.catalog,
            timeseries=providers.timeseries,
        ),
        retrieval=retrieval,
        graph=providers.graph,
    )
