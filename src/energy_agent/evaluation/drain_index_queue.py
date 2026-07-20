import argparse
import asyncio
import json
from collections import defaultdict
from dataclasses import dataclass

from aio_pika.abc import AbstractIncomingMessage
from pydantic import ValidationError

from energy_agent.core.config import Settings
from energy_agent.core.lifecycle import create_tracer
from energy_agent.graph.service import GraphService
from energy_agent.indexing.contracts import (
    IndexJobMessage,
    IndexJobStatus,
    should_dead_letter,
)
from energy_agent.indexing.handlers import (
    IndexHandlers,
    PermanentIndexError,
)
from energy_agent.indexing.publisher import OutboxPublisher
from energy_agent.indexing.repository import IndexRepository
from energy_agent.persistence.mysql import create_mysql_engine, create_session_factory
from energy_agent.providers.embedding import OpenAICompatibleEmbeddingProvider
from energy_agent.providers.milvus import MilvusVectorProvider
from energy_agent.providers.neo4j import Neo4jProvider
from energy_agent.providers.rabbitmq import RabbitMQProvider


@dataclass(frozen=True)
class PendingMessage:
    message: AbstractIncomingMessage
    event: IndexJobMessage
    attempt_count: int
    max_attempts: int


class EvaluationBatchDrainer:
    def __init__(
        self,
        *,
        repository: IndexRepository,
        handlers: IndexHandlers,
        rabbitmq: RabbitMQProvider,
        retry_delay_ms: int,
    ) -> None:
        self.repository = repository
        self.handlers = handlers
        self.rabbitmq = rabbitmq
        self.retry_delay_ms = retry_delay_ms
        self.completed = 0
        self.failed = 0

    async def drain(self, batch_size: int) -> dict[str, int]:
        if not self.rabbitmq.channel:
            raise RuntimeError("RABBITMQ_UNAVAILABLE")
        queue = await self.rabbitmq.channel.get_queue(self.rabbitmq.settings.rabbitmq_index_queue)
        while True:
            messages: list[AbstractIncomingMessage] = []
            for _ in range(batch_size):
                message = await queue.get(fail=False, timeout=1)
                if message is None:
                    break
                messages.append(message)
            if not messages:
                break
            groups: dict[tuple[str, str], list[PendingMessage]] = defaultdict(list)
            for message in messages:
                try:
                    event = IndexJobMessage.model_validate_json(message.body)
                except ValidationError:
                    await message.reject(requeue=False)
                    self.failed += 1
                    continue
                job = await self.repository.start(event.job_id)
                if not job:
                    await message.reject(requeue=False)
                    self.failed += 1
                    continue
                if job.status in {
                    IndexJobStatus.INDEXED,
                    IndexJobStatus.DEGRADED,
                    IndexJobStatus.TOMBSTONED,
                    IndexJobStatus.STALE,
                }:
                    await message.ack()
                    continue
                groups[(str(event.entity_type), str(event.operation))].append(
                    PendingMessage(
                        message=message,
                        event=event,
                        attempt_count=job.attempt_count,
                        max_attempts=job.max_attempts,
                    )
                )
            for group in groups.values():
                await self._process(group)
        return {"completed": self.completed, "failed": self.failed}

    async def _process(self, pending: list[PendingMessage]) -> None:
        try:
            results = await self.handlers.handle_batch([item.event for item in pending])
        except Exception as exc:
            if len(pending) > 1:
                middle = len(pending) // 2
                await self._process(pending[:middle])
                await self._process(pending[middle:])
                return
            await self._fail(pending[0], exc)
            return
        for item in pending:
            result = results[item.event.job_id]
            await self.repository.finish(item.event.job_id, result.status)
            await item.message.ack()
            self.completed += 1

    async def _fail(self, item: PendingMessage, exc: Exception) -> None:
        retryable = not isinstance(exc, PermanentIndexError)
        dead = should_dead_letter(
            item.attempt_count,
            item.max_attempts,
            retryable=retryable,
        )
        error_code = (
            str(exc)
            if isinstance(exc, PermanentIndexError)
            else str(getattr(exc, "code", "INDEX_PROVIDER_UNAVAILABLE"))
        )
        await self.repository.fail(
            item.event.job_id,
            error_code=error_code,
            error_message=type(exc).__name__,
            retry_delay_ms=None if dead else self.retry_delay_ms,
        )
        routing_key = self.rabbitmq.dead_routing_key if dead else self.rabbitmq.retry_routing_key
        await self.rabbitmq.publish(
            json.dumps(item.event.model_dump(mode="json"), separators=(",", ":")).encode(),
            routing_key=routing_key,
        )
        await item.message.ack()
        if dead:
            self.failed += 1


async def run(batch_size: int) -> dict[str, int]:
    settings = Settings()
    if settings.embedding_mode != "openai_compatible":
        raise RuntimeError("EMBEDDING_MODE_MUST_BE_OPENAI_COMPATIBLE")
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
    try:
        await milvus.ensure_collections()
        await rabbitmq.connect()
        publisher = OutboxPublisher(repository, rabbitmq, tracer)
        while await publisher.publish_once(limit=batch_size):
            pass
        drainer = EvaluationBatchDrainer(
            repository=repository,
            handlers=IndexHandlers(
                session_factory=factory,
                embedding=embedding,
                milvus=milvus,
                graph=GraphService(neo4j),
                repository=repository,
                tracer=tracer,
            ),
            rabbitmq=rabbitmq,
            retry_delay_ms=settings.rabbitmq_retry_delay_ms,
        )
        return await drainer.drain(batch_size)
    finally:
        if neo4j:
            await neo4j.close()
        await rabbitmq.close()
        await embedding.close()
        await milvus.close()
        await tracer.flush()
        await tracer.shutdown()
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 256:
        raise SystemExit("--batch-size must be between 1 and 256")
    result = asyncio.run(run(args.batch_size))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
