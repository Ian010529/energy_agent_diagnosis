import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from energy_agent.bootstrap.lifespan import create_tracer
from energy_agent.core.config import Settings
from energy_agent.graph.service import GraphService
from energy_agent.indexing.contracts import (
    EntityType,
    IndexJobCreate,
    IndexOperation,
)
from energy_agent.indexing.handlers import IndexHandlers
from energy_agent.indexing.publisher import OutboxPublisher
from energy_agent.indexing.repository import IndexRepository
from energy_agent.indexing.service import IndexConsumer
from energy_agent.persistence.models import (
    DiagnosisCaseModel,
    GraphProjectionModel,
    IndexJobModel,
    IndexOutboxModel,
    MaintenanceTicketModel,
    ManualChunkModel,
    ManualDocumentModel,
)
from energy_agent.persistence.mysql import create_mysql_engine, create_session_factory
from energy_agent.providers.embedding import OpenAICompatibleEmbeddingProvider
from energy_agent.providers.milvus import MilvusVectorProvider
from energy_agent.providers.neo4j import Neo4jProvider
from energy_agent.providers.rabbitmq import RabbitMQProvider

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    os.getenv("PHASE5_LIVE") != "1",
    reason="requires explicit real embedding/Milvus/RabbitMQ/Neo4j validation",
)
@pytest.mark.asyncio
async def test_real_manual_ticket_case_index_and_case_tombstone() -> None:
    suffix = uuid4().hex[:10]
    settings = Settings(
        app_env="test",
        index_execution_mode="rabbitmq",
        graph_mode="neo4j",
        neo4j_password="energy_neo4j_dev",
        rabbitmq_index_exchange=f"energy.live.test.{suffix}",
        rabbitmq_index_queue=f"energy.live.jobs.test.{suffix}",
        rabbitmq_index_retry_queue=f"energy.live.retry.test.{suffix}",
        rabbitmq_index_dead_queue=f"energy.live.dead.test.{suffix}",
        rabbitmq_retry_delay_ms=200,
    )
    assert settings.embedding_mode == "openai_compatible"
    engine = create_mysql_engine(settings.mysql_dsn)
    factory = create_session_factory(engine)
    repository = IndexRepository(factory)
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
    neo4j = Neo4jProvider(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password or "",
        database=settings.neo4j_database,
        timeout_seconds=settings.neo4j_query_timeout_seconds,
    )
    ids = {
        "doc": f"LIVE-DOC-{suffix}",
        "chunk": f"LIVE-CHUNK-{suffix}",
        "ticket": f"LIVE-TICKET-{suffix}",
        "case": f"LIVE-CASE-{suffix}",
    }
    now = datetime.now(UTC).replace(tzinfo=None)
    generations = {name: uuid4().hex for name in ("manual", "ticket")}
    await rabbitmq.connect()
    assert rabbitmq.channel is not None
    try:
        await milvus.ensure_collections()
        await neo4j.ensure_schema()
        async with factory.begin() as session:
            session.add(
                ManualDocumentModel(
                    doc_id=ids["doc"],
                    document_name="live.txt",
                    object_key="live/object",
                    content_type="text/plain",
                    file_sha256="a" * 64,
                    device_type="PCS",
                    device_model="SC5000",
                    manufacturer="EnergyCo",
                    version="1.0",
                    review_status="APPROVED",
                    effective=True,
                    parser_version="test",
                    chunking_version="test",
                    index_status="QUEUED",
                    index_generation=generations["manual"],
                    chunk_count=1,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add(
                ManualChunkModel(
                    chunk_id=ids["chunk"],
                    doc_id=ids["doc"],
                    device_type="PCS",
                    device_model="SC5000",
                    manufacturer="EnergyCo",
                    alarm_name="PCS机柜温度异常",
                    chapter_title="散热检查",
                    page_no=1,
                    section_type="维护步骤",
                    summary_or_content="检查风扇供电、滤网和风道。",
                    version="1.0",
                    verified=True,
                    effective=True,
                    embedding_text="散热检查\n检查风扇供电、滤网和风道。",
                    index_generation=generations["manual"],
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add(
                MaintenanceTicketModel(
                    ticket_id=ids["ticket"],
                    site_id="SITE-LIVE",
                    device_id="PCS-LIVE",
                    device_model="SC5000",
                    alarm_name="PCS机柜温度异常",
                    fault_symptom="风扇转速为零",
                    root_cause="风扇供电异常",
                    action_taken="检查供电",
                    is_verified=True,
                    close_time=now,
                    manufacturer="EnergyCo",
                    index_status="QUEUED",
                    index_generation=generations["ticket"],
                    updated_at=now,
                )
            )
            session.add(
                DiagnosisCaseModel(
                    case_id=ids["case"],
                    source_session_id=f"LIVE-SESSION-{suffix}",
                    source_run_id=f"LIVE-RUN-{suffix}",
                    source_review_id=f"LIVE-REVIEW-{suffix}",
                    device_type="PCS",
                    device_model="SC5000",
                    manufacturer="EnergyCo",
                    alarm_name="PCS机柜温度异常",
                    symptom_summary="风扇不转且温度升高",
                    timeseries_features="fan_speed=0",
                    root_cause="散热风扇失效或转速异常",
                    resolution_steps=["检查供电并更换风扇"],
                    safety_notes=["断电操作需授权"],
                    evidence_refs=["timeseries:live"],
                    review_status="APPROVED",
                    reviewer="reviewer",
                    case_version=1,
                    index_status="QUEUED",
                    is_active=False,
                    created_by="operator",
                    created_at=now,
                    updated_at=now,
                )
            )
            for entity_type, entity_id, entity_version in (
                (EntityType.MANUAL_DOCUMENT, ids["doc"], generations["manual"]),
                (EntityType.MAINTENANCE_TICKET, ids["ticket"], generations["ticket"]),
                (EntityType.DIAGNOSIS_CASE, ids["case"], "1"),
            ):
                await repository.add_job(
                    session,
                    IndexJobCreate(
                        entity_type=entity_type,
                        entity_id=entity_id,
                        entity_version=entity_version,
                        operation=IndexOperation.UPSERT,
                        trace_id=f"trace-{suffix}",
                        correlation_id=f"correlation-{suffix}",
                        causation_id=f"causation-{suffix}",
                    ),
                )
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
            retry_delay_ms=200,
        )
        assert await OutboxPublisher(repository, rabbitmq, tracer).publish_once() == 3
        queue = await rabbitmq.channel.get_queue(settings.rabbitmq_index_queue)
        for _ in range(3):
            message = await queue.get(no_ack=False, fail=False)
            assert message is not None
            await consumer.consume(message)

        async with factory() as session:
            document = (
                await session.execute(
                    select(ManualDocumentModel).where(ManualDocumentModel.doc_id == ids["doc"])
                )
            ).scalar_one()
            ticket = await session.get(MaintenanceTicketModel, ids["ticket"])
            case = await session.get(DiagnosisCaseModel, ids["case"])
        assert document is not None and document.index_status == "INDEXED"
        assert ticket is not None and ticket.index_status == "INDEXED"
        assert case is not None and case.index_status == "INDEXED" and case.is_active

        query_vector = (await embedding.embed(["风扇不转且温度升高"]))[0]
        assert await milvus.search("case", query_vector, [ids["case"]], 1)

        async with factory.begin() as session:
            case = await session.get(DiagnosisCaseModel, ids["case"], with_for_update=True)
            assert case is not None
            case.review_status = "DISABLED"
            case.is_active = False
            case.index_status = "QUEUED"
            await repository.add_job(
                session,
                IndexJobCreate(
                    entity_type=EntityType.DIAGNOSIS_CASE,
                    entity_id=ids["case"],
                    entity_version="1",
                    operation=IndexOperation.TOMBSTONE,
                    trace_id=f"trace-{suffix}",
                    correlation_id=f"correlation-{suffix}",
                    causation_id=f"disable-{suffix}",
                ),
            )
        assert await OutboxPublisher(repository, rabbitmq, tracer).publish_once() == 1
        tombstone = await queue.get(no_ack=False, fail=False)
        assert tombstone is not None
        await consumer.consume(tombstone)
        assert not await milvus.search("case", query_vector, [ids["case"]], 1)
    finally:
        async with factory.begin() as session:
            job_ids = (
                (
                    await session.execute(
                        select(IndexJobModel.job_id).where(
                            IndexJobModel.entity_id.in_(ids.values())
                        )
                    )
                )
                .scalars()
                .all()
            )
            await session.execute(
                delete(GraphProjectionModel).where(GraphProjectionModel.entity_id.in_(ids.values()))
            )
            await session.execute(
                delete(IndexOutboxModel).where(IndexOutboxModel.job_id.in_(job_ids))
            )
            await session.execute(delete(IndexJobModel).where(IndexJobModel.job_id.in_(job_ids)))
            await session.execute(
                delete(DiagnosisCaseModel).where(DiagnosisCaseModel.case_id == ids["case"])
            )
            await session.execute(
                delete(MaintenanceTicketModel).where(
                    MaintenanceTicketModel.ticket_id == ids["ticket"]
                )
            )
            await session.execute(
                delete(ManualChunkModel).where(ManualChunkModel.chunk_id == ids["chunk"])
            )
            await session.execute(
                delete(ManualDocumentModel).where(ManualDocumentModel.doc_id == ids["doc"])
            )
        await rabbitmq.channel.queue_delete(settings.rabbitmq_index_queue)
        await rabbitmq.channel.queue_delete(settings.rabbitmq_index_retry_queue)
        await rabbitmq.channel.queue_delete(settings.rabbitmq_index_dead_queue)
        await rabbitmq.channel.exchange_delete(settings.rabbitmq_index_exchange)
        await rabbitmq.close()
        await neo4j.close()
        await embedding.close()
        await milvus.close()
        await tracer.flush()
        await tracer.shutdown()
        await engine.dispose()
