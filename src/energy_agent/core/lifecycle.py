import asyncio
import logging
from collections.abc import (
    AsyncIterator,
    Awaitable,
    Callable,
)
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI
from influxdb_client.client.influxdb_client import InfluxDBClient

from energy_agent.core.config import Settings
from energy_agent.core.context import get_context
from energy_agent.core.ids import new_id
from energy_agent.graph.service import GraphService
from energy_agent.indexing.repository import IndexRepository
from energy_agent.memory.session_store import RedisSessionStore
from energy_agent.model.gateway import ModelGateway
from energy_agent.observability.langfuse import LangFuseTracer
from energy_agent.observability.logging import configure_logging, log_event
from energy_agent.observability.tracing import LocalTracer, Tracer
from energy_agent.persistence.mysql import create_mysql_engine, create_session_factory
from energy_agent.persistence.redis import create_redis_client
from energy_agent.persistence.repositories.audit import AuditRepository
from energy_agent.persistence.repositories.cases import CaseRepository
from energy_agent.persistence.repositories.diagnosis_review import DiagnosisReviewRepository
from energy_agent.persistence.repositories.diagnosis_run import (
    DiagnosisResultRepository,
    DiagnosisRunRepository,
)
from energy_agent.persistence.repositories.diagnosis_session import (
    DiagnosisSessionRepository,
)
from energy_agent.persistence.repositories.diagnosis_step_log import (
    DiagnosisStepLogRepository,
)
from energy_agent.providers.embedding import OpenAICompatibleEmbeddingProvider
from energy_agent.providers.influxdb import InfluxTimeseriesProvider
from energy_agent.providers.milvus import MilvusVectorProvider
from energy_agent.providers.minio import MinioDocumentProvider
from energy_agent.providers.mysql import MySQLDiagnosisProvider
from energy_agent.providers.neo4j import Neo4jProvider
from energy_agent.providers.reranker import HttpRerankerProvider
from energy_agent.retrieval.contracts import QueryRewrite, RetrievalMode
from energy_agent.retrieval.scoring import ScoreWeights
from energy_agent.retrieval.service import RetrievalService
from energy_agent.tools.implementations.graph_tools import register_graph_tool
from energy_agent.tools.implementations.read_tools import build_registry
from energy_agent.tools.implementations.review_tools import register_review_tool

logger = logging.getLogger(__name__)


def create_tracer(settings: Settings) -> Tracer:
    if settings.observability_mode == "langfuse":
        assert settings.langfuse_public_key is not None
        assert settings.langfuse_secret_key is not None
        return LangFuseTracer(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
            environment=settings.app_env,
            mode=settings.trace_content_mode,
        )
    return LocalTracer(settings.trace_content_mode)


async def _close(name: str, operation: Awaitable[object]) -> None:
    try:
        async with asyncio.timeout(5.0):
            await operation
    except Exception:
        log_event(logger, logging.ERROR, "resource_close_failed", error_code=name)


def build_lifespan(
    settings: Settings,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_level, settings.log_format)
        tracer = create_tracer(settings)
        engine = create_mysql_engine(settings.mysql_dsn)
        session_factory = create_session_factory(engine)
        redis = create_redis_client(settings.redis_url)
        influx_client = InfluxDBClient(
            url=settings.influxdb_url,
            token=settings.influxdb_token,
            org=settings.influxdb_org,
            timeout=int(settings.influxdb_query_timeout_seconds * 1000),
        )
        mysql_provider = MySQLDiagnosisProvider(session_factory)
        timeseries_provider = InfluxTimeseriesProvider(
            influx_client,
            settings.influxdb_org,
            settings.influxdb_bucket,
            settings.influxdb_query_timeout_seconds,
        )
        model_gateway = (
            ModelGateway(
                base_url=str(
                    settings.openai_base_url
                    if settings.model_mode == "openai"
                    else settings.model_gateway_base_url
                ),
                api_key=str(
                    settings.openai_api_key
                    if settings.model_mode == "openai"
                    else settings.model_gateway_api_key
                ),
                model=settings.model_name,
                timeout_seconds=settings.model_timeout_seconds,
                temperature=settings.model_temperature,
                tracer=tracer,
                api_mode=("responses" if settings.model_mode == "openai" else "chat_completions"),
            )
            if (
                settings.model_mode == "openai"
                and settings.openai_api_key
                or settings.model_mode == "openai_compatible"
                and settings.model_gateway_base_url
                and settings.model_gateway_api_key
            )
            else None
        )
        minio_provider = (
            MinioDocumentProvider(
                endpoint=settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                bucket=settings.minio_bucket_documents,
                secure=settings.minio_secure,
            )
            if settings.retrieval_mode == "hybrid"
            else None
        )
        embedding_provider = (
            OpenAICompatibleEmbeddingProvider(
                base_url=settings.embedding_base_url or "",
                api_key=settings.embedding_api_key or "",
                model=settings.embedding_model,
                dimension=settings.embedding_dimension,
                timeout_seconds=settings.embedding_timeout_seconds,
                batch_size=settings.embedding_batch_size,
            )
            if settings.embedding_mode == "openai_compatible"
            else None
        )
        milvus_provider = (
            MilvusVectorProvider(
                uri=settings.milvus_uri,
                token=settings.milvus_token,
                manual_collection=settings.milvus_manual_collection,
                ticket_collection=settings.milvus_ticket_collection,
                case_collection=settings.milvus_case_collection,
                dimension=settings.milvus_vector_dimension,
                metric_type=settings.milvus_metric_type,
            )
            if settings.retrieval_mode == "hybrid"
            else None
        )
        reranker_provider = (
            HttpRerankerProvider(
                base_url=settings.rerank_base_url or "",
                api_key=settings.rerank_api_key or "",
                model=settings.rerank_model,
                timeout_seconds=settings.rerank_timeout_seconds,
            )
            if settings.rerank_mode == "http"
            else None
        )
        neo4j_provider = (
            Neo4jProvider(
                uri=settings.neo4j_uri,
                user=settings.neo4j_user,
                password=settings.neo4j_password or "",
                database=settings.neo4j_database,
                timeout_seconds=settings.neo4j_query_timeout_seconds,
            )
            if settings.graph_mode == "neo4j"
            else None
        )
        graph_service = GraphService(neo4j_provider)
        if minio_provider:
            await minio_provider.ensure_bucket()
        if milvus_provider:
            await milvus_provider.ensure_collections()

        async def model_rewrite(payload: dict[str, object]) -> object:
            if not model_gateway:
                return payload
            context = get_context()
            result = await model_gateway.generate(
                trace_id=context.trace_id if context else new_id(),
                session_id="retrieval",
                node_name="query_rewrite",
                prompt_version="rag.query_rewrite.v1.0",
                system_prompt=(
                    "只改写检索表达，不输出根因。保留输入中的型号和编号，"
                    "不得生成输入不存在的具体设备信息。"
                ),
                evidence_package=payload,
                output_schema=QueryRewrite,
            )
            return result or payload

        retrieval_service = RetrievalService(
            mysql=mysql_provider,
            tracer=tracer,
            embedding=embedding_provider,
            milvus=milvus_provider,
            reranker=reranker_provider,
            query_rewrite_mode=settings.query_rewrite_mode,
            default_mode=RetrievalMode(settings.retrieval_mode),
            keyword_top_n=max(settings.manual_keyword_top_n, settings.ticket_keyword_top_n),
            vector_top_n=max(settings.manual_vector_top_n, settings.ticket_vector_top_n),
            rerank_input_size=settings.rerank_input_size,
            semantic_dedup_threshold=settings.semantic_dedup_threshold,
            max_chunks_per_document=settings.max_chunks_per_document,
            max_results_per_ticket=settings.max_results_per_ticket,
            weights=ScoreWeights(
                keyword=settings.retrieval_keyword_weight,
                vector=settings.retrieval_vector_weight,
                rerank=settings.retrieval_rerank_weight,
                final_retrieval=settings.final_retrieval_weight,
                source_reliability=settings.final_source_reliability_weight,
                verification=settings.final_verification_weight,
                relevance_to_alarm=settings.final_relevance_to_alarm_weight,
                freshness=settings.final_freshness_weight,
            ),
            model_rewrite=model_rewrite
            if settings.query_rewrite_mode == "model_enhanced"
            else None,
        )

        app.state.settings = settings
        app.state.tracer = tracer
        app.state.mysql_engine = engine
        app.state.redis = redis
        app.state.influx_client = influx_client
        app.state.session_repository = DiagnosisSessionRepository(session_factory, tracer)
        app.state.step_log_repository = DiagnosisStepLogRepository(session_factory, tracer)
        app.state.run_repository = DiagnosisRunRepository(session_factory, tracer)
        app.state.result_repository = DiagnosisResultRepository(session_factory, tracer)
        app.state.mysql_provider = mysql_provider
        app.state.timeseries_provider = timeseries_provider
        app.state.minio_provider = minio_provider
        app.state.embedding_provider = embedding_provider
        app.state.milvus_provider = milvus_provider
        app.state.reranker_provider = reranker_provider
        app.state.retrieval_service = retrieval_service
        app.state.graph_service = graph_service
        app.state.audit_repository = AuditRepository(session_factory, tracer)
        app.state.index_repository = IndexRepository(session_factory, tracer)
        app.state.case_repository = CaseRepository(session_factory, app.state.index_repository)
        app.state.review_repository = DiagnosisReviewRepository(session_factory)
        app.state.tool_registry = build_registry(
            mysql_provider, timeseries_provider, tracer, retrieval_service
        )
        register_graph_tool(app.state.tool_registry, graph_service, tracer)
        register_review_tool(app.state.tool_registry, app.state.review_repository)
        app.state.model_gateway = model_gateway
        app.state.session_store = RedisSessionStore(
            redis, settings.redis_session_ttl_seconds, tracer
        )
        log_event(logger, logging.INFO, "application_started")
        try:
            yield
        finally:
            if embedding_provider:
                await _close("embedding", embedding_provider.close())
            if reranker_provider:
                await _close("reranker", reranker_provider.close())
            if milvus_provider:
                await _close("milvus", milvus_provider.close())
            if neo4j_provider:
                await _close("neo4j", neo4j_provider.close())
            await _close("tracer_flush", tracer.flush())
            await _close("tracer_shutdown", tracer.shutdown())
            await _close("redis", redis.aclose())
            await _close("influxdb", asyncio.to_thread(influx_client.close))
            await _close("mysql", engine.dispose())
            log_event(logger, logging.INFO, "application_stopped")

    return lifespan
