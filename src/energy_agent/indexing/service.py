import json
import logging
from time import monotonic

from aio_pika.abc import AbstractIncomingMessage
from pydantic import ValidationError

from energy_agent.core.context import ServiceActorContext
from energy_agent.indexing.contracts import (
    EntityType,
    IndexJobMessage,
    IndexJobStatus,
    should_dead_letter,
)
from energy_agent.indexing.handlers import (
    IndexHandlers,
    PermanentIndexError,
    StaleIndexEventError,
)
from energy_agent.indexing.ports import (
    IndexAuditPort,
    IndexConsumerRepositoryPort,
    IndexMessagePort,
)
from energy_agent.observability.logging import log_event
from energy_agent.observability.metrics import (
    GRAPH_PROJECTION,
    INDEX_DEAD_LETTERS,
    INDEX_JOB_DURATION,
    INDEX_JOBS,
    INDEX_RETRIES,
)
from energy_agent.observability.tracing import Tracer

logger = logging.getLogger(__name__)


class IndexConsumer:
    def __init__(
        self,
        *,
        repository: IndexConsumerRepositoryPort,
        handlers: IndexHandlers,
        rabbitmq: IndexMessagePort,
        tracer: Tracer,
        retry_delay_ms: int,
        audit: IndexAuditPort | None = None,
    ) -> None:
        self.repository = repository
        self.handlers = handlers
        self.rabbitmq = rabbitmq
        self.tracer = tracer
        self.retry_delay_ms = retry_delay_ms
        self.audit = audit
        self.actor = ServiceActorContext(actor_id="service:index-worker")

    async def consume(self, message: AbstractIncomingMessage) -> None:
        started = monotonic()
        try:
            event = IndexJobMessage.model_validate_json(message.body)
        except ValidationError:
            log_event(
                logger,
                logging.ERROR,
                "index_event_invalid",
                error_code="INDEX_EVENT_INVALID",
            )
            await message.reject(requeue=False)
            INDEX_JOBS.labels(status="invalid").inc()
            return
        job = await self.repository.start(event.job_id)
        if not job:
            await self.rabbitmq.publish(message.body, routing_key=self.rabbitmq.dead_routing_key)
            await message.ack()
            INDEX_JOBS.labels(status="missing").inc()
            return
        if job.status in {
            IndexJobStatus.INDEXED,
            IndexJobStatus.DEGRADED,
            IndexJobStatus.TOMBSTONED,
            IndexJobStatus.STALE,
        }:
            await message.ack()
            INDEX_JOBS.labels(status="idempotent_replay").inc()
            return
        await self._audit(event, "index.started", status=IndexJobStatus.RUNNING)
        with self.tracer.start_span(
            "index.message.consume",
            trace_id=event.trace_id,
            metadata={
                "job_id": event.job_id,
                "entity_type": event.entity_type,
                "entity_version": event.entity_version,
                "attempt": job.attempt_count,
            },
        ) as span:
            try:
                result = await self.handlers.handle(event)
                await self.repository.finish(event.job_id, result.status)
                INDEX_JOBS.labels(status=result.status).inc()
                INDEX_JOB_DURATION.labels(
                    entity_type=event.entity_type, status=result.status
                ).observe(monotonic() - started)
                span.set_output({"status": result.status})
                action = (
                    "index.degraded"
                    if result.status == IndexJobStatus.DEGRADED
                    else "index.succeeded"
                )
                await self._audit(event, action, status=result.status)
                if event.entity_type == EntityType.DIAGNOSIS_CASE:
                    GRAPH_PROJECTION.labels(
                        status=("degraded" if result.graph_degraded else str(result.status).lower())
                    ).inc()
                    graph_action = (
                        "graph.tombstoned"
                        if result.status == IndexJobStatus.TOMBSTONED
                        else "graph.degraded"
                        if result.graph_degraded
                        else "graph.projected"
                    )
                    await self._audit(event, graph_action, status=result.status)
                await message.ack()
            except StaleIndexEventError:
                await self.repository.finish(event.job_id, IndexJobStatus.STALE)
                INDEX_JOBS.labels(status=IndexJobStatus.STALE).inc()
                INDEX_JOB_DURATION.labels(
                    entity_type=event.entity_type, status=IndexJobStatus.STALE
                ).observe(monotonic() - started)
                span.set_output({"status": IndexJobStatus.STALE})
                await message.ack()
            except Exception as exc:
                retryable = not isinstance(exc, PermanentIndexError)
                dead = should_dead_letter(
                    job.attempt_count,
                    job.max_attempts,
                    retryable=retryable,
                )
                error_code = (
                    str(exc)
                    if isinstance(exc, PermanentIndexError)
                    else getattr(exc, "code", "INDEX_PROVIDER_UNAVAILABLE")
                )
                await self.repository.fail(
                    event.job_id,
                    error_code=str(error_code),
                    error_message=type(exc).__name__,
                    retry_delay_ms=None if dead else self.retry_delay_ms,
                )
                INDEX_JOBS.labels(status=IndexJobStatus.FAILED if dead else "retrying").inc()
                INDEX_JOB_DURATION.labels(
                    entity_type=event.entity_type,
                    status=IndexJobStatus.FAILED if dead else "retrying",
                ).observe(monotonic() - started)
                if dead:
                    INDEX_DEAD_LETTERS.labels(entity_type=event.entity_type).inc()
                else:
                    INDEX_RETRIES.labels(entity_type=event.entity_type).inc()
                span.record_error(exc)
                if dead:
                    await self._audit(
                        event,
                        "index.failed",
                        status=IndexJobStatus.FAILED,
                        outcome="failed",
                        error_code=str(error_code),
                    )
                await self._audit(
                    event,
                    "index.dead_lettered" if dead else "index.retried",
                    status=IndexJobStatus.FAILED if dead else IndexJobStatus.QUEUED,
                    outcome="failed" if dead else "retrying",
                    error_code=str(error_code),
                )
                routing_key = (
                    self.rabbitmq.dead_routing_key if dead else self.rabbitmq.retry_routing_key
                )
                with self.tracer.start_span(
                    "index.dead_letter" if dead else "index.retry",
                    trace_id=event.trace_id,
                    metadata={
                        "job_id": event.job_id,
                        "entity_type": event.entity_type,
                        "entity_version": event.entity_version,
                        "attempt": job.attempt_count,
                        "status": "FAILED" if dead else "QUEUED",
                    },
                ):
                    await self.rabbitmq.publish(
                        json.dumps(
                            event.model_dump(mode="json"),
                            separators=(",", ":"),
                        ).encode(),
                        routing_key=routing_key,
                    )
                await message.ack()

    async def _audit(
        self,
        event: IndexJobMessage,
        action: str,
        *,
        status: IndexJobStatus,
        outcome: str = "succeeded",
        error_code: str | None = None,
    ) -> None:
        if not self.audit:
            return
        try:
            await self.audit.write(
                actor=self.actor,
                action=action,
                resource_type="index_job",
                resource_id=event.job_id,
                trace_id=event.trace_id,
                outcome=outcome,
                case_id=(
                    event.entity_id if event.entity_type == EntityType.DIAGNOSIS_CASE else None
                ),
                snapshot={
                    "actor_kind": self.actor.actor_kind,
                    "entity_type": event.entity_type,
                    "entity_version": event.entity_version,
                    "operation": event.operation,
                    "status": status,
                    "error_code": error_code,
                },
            )
        except Exception:
            log_event(
                logger,
                logging.ERROR,
                "index_audit_failed",
                job_id=event.job_id,
                error_code="INDEX_AUDIT_WRITE_FAILED",
            )
