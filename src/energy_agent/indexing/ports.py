from collections.abc import Sequence
from typing import Any, Protocol

from energy_agent.core.context import ActorContext, ServiceActorContext
from energy_agent.indexing.contracts import IndexJobRecord, IndexJobStatus


class EmbeddingPort(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class VectorIndexPort(Protocol):
    async def upsert(self, source: str, rows: list[dict[str, Any]]) -> None: ...

    async def delete(self, source: str, ids: list[str]) -> None: ...


class IndexMessagePort(Protocol):
    dead_routing_key: str
    retry_routing_key: str

    async def publish(self, body: bytes, *, routing_key: str | None = None) -> None: ...


class IndexAuditPort(Protocol):
    async def write(
        self,
        *,
        actor: ActorContext | ServiceActorContext,
        action: str,
        resource_type: str,
        resource_id: str,
        trace_id: str,
        outcome: str = "succeeded",
        session_id: str | None = None,
        case_id: str | None = None,
        snapshot: dict[str, Any] | None = None,
    ) -> None: ...


class IndexConsumerRepositoryPort(Protocol):
    async def start(self, job_id: str) -> IndexJobRecord | None: ...

    async def finish(self, job_id: str, status: IndexJobStatus) -> None: ...

    async def fail(
        self,
        job_id: str,
        *,
        error_code: str,
        error_message: str,
        retry_delay_ms: int | None,
    ) -> None: ...


class OutboxRecordPort(Protocol):
    id: int
    job_id: str
    payload: dict[str, Any]


class IndexOutboxRepositoryPort(Protocol):
    async def pending_outbox(self, limit: int = 50) -> Sequence[OutboxRecordPort]: ...

    async def mark_published(self, outbox_id: int, job_id: str) -> None: ...

    async def mark_publish_failed(self, outbox_id: int, error_code: str) -> None: ...
