from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from energy_agent.core.config import Settings
from energy_agent.indexing.contracts import (
    EntityType,
    IndexJobCreate,
    IndexJobStatus,
    IndexOperation,
)
from energy_agent.indexing.handlers import HandlerResult
from energy_agent.indexing.publisher import OutboxPublisher
from energy_agent.indexing.repository import IndexRepository
from energy_agent.indexing.service import IndexConsumer
from energy_agent.observability.tracing import LocalTracer
from energy_agent.persistence.models import IndexJobModel, IndexOutboxModel
from energy_agent.persistence.mysql import create_mysql_engine, create_session_factory
from energy_agent.providers.rabbitmq import RabbitMQProvider

pytestmark = pytest.mark.integration


class _SuccessfulHandlers:
    async def handle(self, _: object) -> HandlerResult:
        return HandlerResult(IndexJobStatus.INDEXED)


@pytest.mark.asyncio
async def test_outbox_confirm_worker_manual_ack_and_duplicate_job_idempotency() -> None:
    suffix = uuid4().hex[:10]
    settings = Settings(
        app_env="test",
        index_execution_mode="rabbitmq",
        rabbitmq_index_exchange=f"energy.worker.test.{suffix}",
        rabbitmq_index_queue=f"energy.worker.jobs.test.{suffix}",
        rabbitmq_index_retry_queue=f"energy.worker.retry.test.{suffix}",
        rabbitmq_index_dead_queue=f"energy.worker.dead.test.{suffix}",
        rabbitmq_retry_delay_ms=200,
    )
    engine = create_mysql_engine(settings.mysql_dsn)
    factory = create_session_factory(engine)
    repository = IndexRepository(factory)
    rabbitmq = RabbitMQProvider(settings)
    await rabbitmq.connect()
    assert rabbitmq.channel is not None
    try:
        request = IndexJobCreate(
            entity_type=EntityType.TEMPLATE_GRAPH,
            entity_id=f"pcs_temperature_abnormal_v1_{suffix}",
            entity_version="1.0.0",
            operation=IndexOperation.GRAPH_PROJECT,
            trace_id="trace-worker",
            correlation_id="bootstrap",
            causation_id="bootstrap",
        )
        first = await repository.create_job(request)
        duplicate = await repository.create_job(request)
        assert duplicate.job_id == first.job_id
        assert await OutboxPublisher(repository, rabbitmq, LocalTracer()).publish_once() == 1

        queue = await rabbitmq.channel.get_queue(settings.rabbitmq_index_queue)
        message = await queue.get(no_ack=False, fail=False)
        assert message is not None
        consumer = IndexConsumer(
            repository=repository,
            handlers=_SuccessfulHandlers(),  # type: ignore[arg-type]
            rabbitmq=rabbitmq,
            tracer=LocalTracer(),
            retry_delay_ms=200,
        )
        await consumer.consume(message)
        completed = await repository.get(first.job_id)
        assert completed is not None
        assert completed.status == IndexJobStatus.INDEXED
        assert completed.attempt_count == 1
        async with factory() as session:
            outboxes = (
                (
                    await session.execute(
                        select(IndexOutboxModel).where(IndexOutboxModel.job_id == first.job_id)
                    )
                )
                .scalars()
                .all()
            )
        assert len(outboxes) == 1
        assert outboxes[0].publish_status == "PUBLISHED"
    finally:
        async with factory.begin() as session:
            if "first" in locals():
                await session.execute(
                    delete(IndexOutboxModel).where(IndexOutboxModel.job_id == first.job_id)
                )
                await session.execute(
                    delete(IndexJobModel).where(IndexJobModel.job_id == first.job_id)
                )
        await rabbitmq.channel.queue_delete(settings.rabbitmq_index_queue)
        await rabbitmq.channel.queue_delete(settings.rabbitmq_index_retry_queue)
        await rabbitmq.channel.queue_delete(settings.rabbitmq_index_dead_queue)
        await rabbitmq.channel.exchange_delete(settings.rabbitmq_index_exchange)
        await rabbitmq.close()
        await engine.dispose()
