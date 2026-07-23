from dataclasses import dataclass

from influxdb_client.client.influxdb_client import InfluxDBClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from energy_agent.agent.service import DiagnosisService
from energy_agent.cases.service import CaseService
from energy_agent.catalog.repository import CatalogRepository
from energy_agent.catalog.service import CatalogService
from energy_agent.core.config import Settings
from energy_agent.evidence.service import EvidenceService
from energy_agent.graph.service import GraphService
from energy_agent.indexing.repository import IndexRepository
from energy_agent.memory.session_store import RedisSessionStore
from energy_agent.model.gateway import ModelGateway
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
from energy_agent.providers.embedding import OpenAICompatibleEmbeddingProvider
from energy_agent.providers.influxdb import InfluxTimeseriesProvider
from energy_agent.providers.milvus import MilvusVectorProvider
from energy_agent.providers.minio import MinioDocumentProvider
from energy_agent.providers.mysql import MySQLDiagnosisProvider
from energy_agent.providers.reranker import HttpRerankerProvider
from energy_agent.reliability.rate_limit import RateLimiter
from energy_agent.reliability.registry import CircuitBreakerRegistry
from energy_agent.retrieval.service import RetrievalService
from energy_agent.timeline.repository import TimelineRepository
from energy_agent.timeline.service import TimelineService
from energy_agent.tools.registry import ToolRegistry


@dataclass(slots=True)
class RepositoryContainer:
    sessions: DiagnosisSessionRepository
    steps: DiagnosisStepLogRepository
    runs: DiagnosisRunRepository
    results: DiagnosisResultRepository
    audit: AuditRepository
    alarm_dedup: AlarmDedupRepository
    indexes: IndexRepository
    cases: CaseRepository
    reviews: DiagnosisReviewRepository
    catalog: CatalogRepository
    timeline: TimelineRepository


@dataclass(slots=True)
class ProviderContainer:
    mysql_engine: AsyncEngine
    mysql_sessions: async_sessionmaker[AsyncSession]
    redis: Redis
    influx_client: InfluxDBClient
    operational_data: MySQLDiagnosisProvider
    timeseries: InfluxTimeseriesProvider
    minio: MinioDocumentProvider | None
    embedding: OpenAICompatibleEmbeddingProvider | None
    vector_search: MilvusVectorProvider | None
    reranker: HttpRerankerProvider | None
    model: ModelGateway | None
    graph: GraphService


@dataclass(slots=True)
class ServiceContainer:
    diagnosis: DiagnosisService
    cases: CaseService
    catalog: CatalogService
    timeline: TimelineService
    evidence: EvidenceService
    retrieval: RetrievalService
    graph: GraphService


@dataclass(slots=True)
class ApplicationContainer:
    settings: Settings
    tracer: Tracer
    rate_limiter: RateLimiter
    repositories: RepositoryContainer
    providers: ProviderContainer
    services: ServiceContainer
    tool_registry: ToolRegistry
    session_store: RedisSessionStore
    circuit_breakers: CircuitBreakerRegistry
