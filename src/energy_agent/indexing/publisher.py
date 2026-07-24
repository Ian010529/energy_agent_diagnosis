import asyncio
import json
import logging

from energy_agent.core.context import ServiceActorContext
from energy_agent.indexing.ports import (
    IndexAuditPort,
    IndexMessagePort,
    IndexOutboxRepositoryPort,
)
from energy_agent.observability.logging import log_event
from energy_agent.observability.metrics import OUTBOX_PUBLISH
from energy_agent.observability.tracing import Tracer

logger = logging.getLogger(__name__)


class OutboxPublisher:
    def __init__(
        self,
        repository: IndexOutboxRepositoryPort,
        rabbitmq: IndexMessagePort,
        tracer: Tracer,
        audit: IndexAuditPort | None = None,
    ) -> None:
        self.repository = repository
        self.rabbitmq = rabbitmq
        self.tracer = tracer
        self.audit = audit
        self.actor = ServiceActorContext(actor_id="service:index-worker")

    async def publish_once(self, limit: int = 50) -> int:
        published = 0
        for row in await self.repository.pending_outbox(limit):
            payload = row.payload
            trace_id = str(payload.get("trace_id", ""))
            try:
                with self.tracer.start_span(
                    "index.outbox.publish",
                    trace_id=trace_id,
                    metadata={"job_id": row.job_id, "outbox_id": row.id},
                ):
                    await self.rabbitmq.publish(json.dumps(payload, separators=(",", ":")).encode())
                await self.repository.mark_published(row.id, row.job_id)
                OUTBOX_PUBLISH.labels(status="published").inc()
                await self._audit_queued(
                    job_id=row.job_id,
                    trace_id=trace_id,
                    entity_type=str(payload.get("entity_type", "")),
                )
                published += 1
            except Exception:
                OUTBOX_PUBLISH.labels(status="failed").inc()
                await self.repository.mark_publish_failed(row.id, "INDEX_OUTBOX_PUBLISH_FAILED")
                log_event(
                    logger,
                    logging.ERROR,
                    "index_outbox_publish_failed",
                    job_id=row.job_id,
                    error_code="INDEX_OUTBOX_PUBLISH_FAILED",
                )
        return published

    async def _audit_queued(self, *, job_id: str, trace_id: str, entity_type: str) -> None:
        if not self.audit:
            return
        try:
            await self.audit.write(
                actor=self.actor,
                action="index.queued",
                resource_type="index_job",
                resource_id=job_id,
                trace_id=trace_id,
                snapshot={
                    "actor_kind": self.actor.actor_kind,
                    "entity_type": entity_type,
                    "status": "QUEUED",
                },
            )
        except Exception:
            log_event(
                logger,
                logging.ERROR,
                "index_audit_failed",
                job_id=job_id,
                error_code="INDEX_AUDIT_WRITE_FAILED",
            )

    async def run(self, poll_interval_seconds: float) -> None:
        while True:
            await self.publish_once()
            await asyncio.sleep(poll_interval_seconds)
