from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from energy_agent.graph.service import GraphService
from energy_agent.indexing.case_handler import CaseIndexHandler
from energy_agent.indexing.contracts import EntityType, IndexJobMessage
from energy_agent.indexing.handler_runtime import (
    HandlerResult,
    IndexHandlerRuntime,
    PermanentIndexError,
    StaleIndexEventError,
)
from energy_agent.indexing.manual_handler import ManualIndexHandler
from energy_agent.indexing.ports import EmbeddingPort, VectorIndexPort
from energy_agent.indexing.repository import IndexRepository
from energy_agent.indexing.ticket_handler import TicketIndexHandler
from energy_agent.observability.tracing import Tracer

__all__ = [
    "HandlerResult",
    "IndexHandlers",
    "PermanentIndexError",
    "StaleIndexEventError",
]


class EntityIndexHandler(Protocol):
    async def handle(self, event: IndexJobMessage) -> HandlerResult: ...

    async def handle_batch(self, events: list[IndexJobMessage]) -> dict[str, HandlerResult]: ...


class IndexHandlers:
    """Dispatcher façade preserving index event and batch semantics."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        embedding: EmbeddingPort,
        milvus: VectorIndexPort,
        graph: GraphService,
        repository: IndexRepository | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        runtime = IndexHandlerRuntime(
            session_factory=session_factory,
            embedding=embedding,
            milvus=milvus,
            graph=graph,
            repository=repository,
            tracer=tracer,
        )
        self._runtime = runtime
        self._handlers: dict[EntityType, EntityIndexHandler] = {
            EntityType.MANUAL_DOCUMENT: ManualIndexHandler(runtime),
            EntityType.MAINTENANCE_TICKET: TicketIndexHandler(runtime),
            EntityType.DIAGNOSIS_CASE: CaseIndexHandler(runtime),
        }

    async def handle(self, event: IndexJobMessage) -> HandlerResult:
        handler = self._handlers.get(event.entity_type)
        if handler is None:
            return await self._runtime.handle(event)
        return await handler.handle(event)

    async def handle_batch(self, events: list[IndexJobMessage]) -> dict[str, HandlerResult]:
        if not events:
            return {}
        handler = self._handlers.get(events[0].entity_type)
        if handler is None:
            return await self._runtime.handle_batch(events)
        return await handler.handle_batch(events)
