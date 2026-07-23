from typing import Any, Protocol

from energy_agent.core.context import ActorContext, ServiceActorContext


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
