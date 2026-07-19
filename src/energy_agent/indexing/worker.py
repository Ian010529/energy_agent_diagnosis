import asyncio

from energy_agent.core.config import Settings
from energy_agent.core.lifecycle import create_tracer
from energy_agent.graph.service import GraphService
from energy_agent.indexing.handlers import IndexHandlers
from energy_agent.indexing.publisher import OutboxPublisher
from energy_agent.indexing.repository import IndexRepository
from energy_agent.indexing.service import IndexConsumer
from energy_agent.persistence.mysql import create_mysql_engine, create_session_factory
from energy_agent.persistence.repositories.audit import AuditRepository
from energy_agent.providers.embedding import OpenAICompatibleEmbeddingProvider
from energy_agent.providers.milvus import MilvusVectorProvider
from energy_agent.providers.neo4j import Neo4jProvider
from energy_agent.providers.rabbitmq import RabbitMQProvider


async def run() -> None:
    settings = Settings()
    if settings.index_execution_mode != "rabbitmq":
        raise RuntimeError("index-worker requires INDEX_EXECUTION_MODE=rabbitmq")
    if settings.embedding_mode != "openai_compatible":
        raise RuntimeError("index-worker requires EMBEDDING_MODE=openai_compatible")
    engine = create_mysql_engine(settings.mysql_dsn)
    factory = create_session_factory(engine)
    tracer = create_tracer(settings)
    rabbitmq = RabbitMQProvider(settings)
    embedding = OpenAICompatibleEmbeddingProvider(
        base_url=settings.embedding_base_url or "",
        api_key=settings.embedding_api_key or "",
        model=settings.embedding_model,
        dimension=settings.embedding_dimension,
        timeout_seconds=settings.embedding_timeout_seconds,
        batch_size=settings.embedding_batch_size,
    )
    milvus = MilvusVectorProvider(
        uri=settings.milvus_uri,
        token=settings.milvus_token,
        manual_collection=settings.milvus_manual_collection,
        ticket_collection=settings.milvus_ticket_collection,
        case_collection=settings.milvus_case_collection,
        dimension=settings.milvus_vector_dimension,
        metric_type=settings.milvus_metric_type,
    )
    neo4j = (
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
    repository = IndexRepository(factory, tracer)
    audit = AuditRepository(factory, tracer)
    try:
        await milvus.ensure_collections()
        await rabbitmq.connect()
        handlers = IndexHandlers(
            session_factory=factory,
            embedding=embedding,
            milvus=milvus,
            graph=GraphService(neo4j),
            repository=repository,
            tracer=tracer,
        )
        consumer = IndexConsumer(
            repository=repository,
            handlers=handlers,
            rabbitmq=rabbitmq,
            tracer=tracer,
            retry_delay_ms=settings.rabbitmq_retry_delay_ms,
            audit=audit,
        )
        publisher = OutboxPublisher(repository, rabbitmq, tracer, audit)
        await rabbitmq.consume(consumer.consume)
        await publisher.run(settings.index_publish_poll_interval_seconds)
    finally:
        if neo4j:
            await neo4j.close()
        await rabbitmq.close()
        await embedding.close()
        await milvus.close()
        await tracer.flush()
        await tracer.shutdown()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
