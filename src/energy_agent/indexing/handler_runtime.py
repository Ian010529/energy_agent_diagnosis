import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from energy_agent.core.ids import new_id
from energy_agent.core.time import utc_now
from energy_agent.graph.contracts import GraphProjectionStatus
from energy_agent.graph.service import GraphService
from energy_agent.indexing.contracts import (
    EntityType,
    IndexJobCreate,
    IndexJobMessage,
    IndexJobStatus,
    IndexOperation,
)
from energy_agent.indexing.ports import EmbeddingPort, VectorIndexPort
from energy_agent.indexing.repository import IndexRepository
from energy_agent.observability.tracing import Tracer
from energy_agent.persistence.models import (
    DiagnosisCaseModel,
    GraphProjectionModel,
    MaintenanceTicketModel,
    ManualChunkModel,
    ManualDocumentModel,
)


class StaleIndexEventError(RuntimeError):
    pass


class PermanentIndexError(RuntimeError):
    pass


@dataclass(frozen=True)
class HandlerResult:
    status: IndexJobStatus
    graph_degraded: bool = False


class IndexHandlerRuntime:
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
        self.session_factory = session_factory
        self.embedding = embedding
        self.milvus = milvus
        self.graph = graph
        self.repository = repository
        self.tracer = tracer

    async def handle(self, event: IndexJobMessage) -> HandlerResult:
        span_name = {
            EntityType.MANUAL_DOCUMENT: "index.manual.upsert",
            EntityType.MAINTENANCE_TICKET: "index.ticket.upsert",
            EntityType.DIAGNOSIS_CASE: (
                "index.tombstone"
                if event.operation == IndexOperation.TOMBSTONE
                else "index.case.upsert"
            ),
        }.get(event.entity_type)
        if not span_name:
            raise PermanentIndexError("INDEX_EVENT_INVALID")
        if self.tracer:
            with self.tracer.start_span(
                span_name,
                trace_id=event.trace_id,
                metadata={
                    "job_id": event.job_id,
                    "entity_id": event.entity_id,
                    "entity_version": event.entity_version,
                },
            ):
                return await self._dispatch(event)
        return await self._dispatch(event)

    async def handle_batch(self, events: list[IndexJobMessage]) -> dict[str, HandlerResult]:
        """Process homogeneous UPSERT batches without changing per-entity state semantics."""
        if not events:
            return {}
        entity_types = {event.entity_type for event in events}
        operations = {event.operation for event in events}
        if (
            len(entity_types) != 1
            or len(operations) != 1
            or not operations.issubset({IndexOperation.UPSERT, IndexOperation.REINDEX})
        ):
            return {event.job_id: await self.handle(event) for event in events}
        entity_type = events[0].entity_type
        if entity_type == EntityType.MAINTENANCE_TICKET:
            return await self._ticket_batch(events)
        if entity_type == EntityType.DIAGNOSIS_CASE:
            return await self._case_batch(events)
        return {event.job_id: await self.handle(event) for event in events}

    async def _dispatch(self, event: IndexJobMessage) -> HandlerResult:
        if event.entity_type == EntityType.MANUAL_DOCUMENT:
            return await self._manual(event)
        if event.entity_type == EntityType.MAINTENANCE_TICKET:
            return await self._ticket(event)
        return await self._case(event)

    async def _manual(self, event: IndexJobMessage) -> HandlerResult:
        async with self.session_factory() as session:
            document = (
                await session.execute(
                    select(ManualDocumentModel).where(
                        ManualDocumentModel.doc_id == event.entity_id,
                        ManualDocumentModel.index_generation == event.entity_version,
                    )
                )
            ).scalar_one_or_none()
            if not document:
                raise PermanentIndexError("INDEX_ENTITY_NOT_FOUND")
            if (
                not document.effective
                or document.review_status != "APPROVED"
                or document.index_generation != event.entity_version
            ):
                raise StaleIndexEventError("INDEX_EVENT_STALE")
            chunks = (
                (
                    await session.execute(
                        select(ManualChunkModel).where(
                            ManualChunkModel.doc_id == event.entity_id,
                            ManualChunkModel.version == document.version,
                        )
                    )
                )
                .scalars()
                .all()
            )
        texts = [chunk.embedding_text or chunk.summary_or_content for chunk in chunks]
        vectors = await self.embedding.embed(texts)
        rows: list[dict[str, Any]] = [
            {
                "id": chunk.chunk_id,
                "source_id": document.doc_id,
                "device_type": document.device_type,
                "device_model": document.device_model or "",
                "manufacturer": document.manufacturer or "",
                "alarm_name": chunk.alarm_name or "",
                "index_generation": document.index_generation or "",
                "verified": True,
                "effective": True,
                "embedding": vector,
            }
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        await self.milvus.upsert("manual", rows)
        now = utc_now()
        async with self.session_factory.begin() as session:
            await session.execute(
                update(ManualDocumentModel)
                .where(
                    ManualDocumentModel.doc_id == event.entity_id,
                    ManualDocumentModel.version == document.version,
                    ManualDocumentModel.effective.is_(True),
                )
                .values(index_status="INDEXED", index_error_code=None, updated_at=now)
            )
            await session.execute(
                update(ManualChunkModel)
                .where(
                    ManualChunkModel.doc_id == event.entity_id,
                    ManualChunkModel.version == document.version,
                )
                .values(indexed_at=now, updated_at=now)
            )
        return HandlerResult(IndexJobStatus.INDEXED)

    async def _ticket(self, event: IndexJobMessage) -> HandlerResult:
        async with self.session_factory() as session:
            ticket = await session.get(MaintenanceTicketModel, event.entity_id)
        if not ticket:
            raise PermanentIndexError("INDEX_ENTITY_NOT_FOUND")
        if ticket.index_generation != event.entity_version or not ticket.is_verified:
            raise StaleIndexEventError("INDEX_EVENT_STALE")
        text = re.sub(
            r"\s+",
            " ",
            " ".join(
                str(value)
                for value in (
                    ticket.device_model,
                    ticket.alarm_name,
                    ticket.fault_symptom,
                    ticket.root_cause,
                    ticket.action_taken,
                )
                if value
            ),
        ).strip()
        vector = (await self.embedding.embed([text]))[0]
        await self.milvus.upsert(
            "ticket",
            [
                {
                    "id": ticket.ticket_id,
                    "source_id": ticket.ticket_id,
                    "device_type": "",
                    "device_model": ticket.device_model,
                    "manufacturer": ticket.manufacturer or "",
                    "alarm_name": ticket.alarm_name,
                    "index_generation": event.entity_version,
                    "verified": True,
                    "effective": True,
                    "close_time": int(ticket.close_time.timestamp()) if ticket.close_time else 0,
                    "embedding": vector,
                }
            ],
        )
        async with self.session_factory.begin() as session:
            await session.execute(
                update(MaintenanceTicketModel)
                .where(
                    MaintenanceTicketModel.ticket_id == event.entity_id,
                    MaintenanceTicketModel.is_verified.is_(True),
                )
                .values(
                    embedding_text=text,
                    index_status="INDEXED",
                    index_error_code=None,
                    indexed_at=utc_now(),
                    updated_at=utc_now(),
                )
            )
        return HandlerResult(IndexJobStatus.INDEXED)

    async def _ticket_batch(self, events: list[IndexJobMessage]) -> dict[str, HandlerResult]:
        async with self.session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(MaintenanceTicketModel).where(
                            MaintenanceTicketModel.ticket_id.in_(
                                [event.entity_id for event in events]
                            )
                        )
                    )
                )
                .scalars()
                .all()
            )
        tickets = {row.ticket_id: row for row in rows}
        ordered: list[tuple[IndexJobMessage, MaintenanceTicketModel, str]] = []
        for event in events:
            ticket = tickets.get(event.entity_id)
            if not ticket:
                raise PermanentIndexError("INDEX_ENTITY_NOT_FOUND")
            if ticket.index_generation != event.entity_version or not ticket.is_verified:
                raise StaleIndexEventError("INDEX_EVENT_STALE")
            text = re.sub(
                r"\s+",
                " ",
                " ".join(
                    str(value)
                    for value in (
                        ticket.device_model,
                        ticket.alarm_name,
                        ticket.fault_symptom,
                        ticket.root_cause,
                        ticket.action_taken,
                    )
                    if value
                ),
            ).strip()
            ordered.append((event, ticket, text))
        vectors = await self.embedding.embed([item[2] for item in ordered])
        await self.milvus.upsert(
            "ticket",
            [
                {
                    "id": ticket.ticket_id,
                    "source_id": ticket.ticket_id,
                    "device_type": "",
                    "device_model": ticket.device_model,
                    "manufacturer": ticket.manufacturer or "",
                    "alarm_name": ticket.alarm_name,
                    "index_generation": event.entity_version,
                    "verified": True,
                    "effective": True,
                    "close_time": int(ticket.close_time.timestamp()) if ticket.close_time else 0,
                    "embedding": vector,
                }
                for (event, ticket, _), vector in zip(ordered, vectors, strict=True)
            ],
        )
        now = utc_now()
        async with self.session_factory.begin() as session:
            for event, _, text in ordered:
                await session.execute(
                    update(MaintenanceTicketModel)
                    .where(
                        MaintenanceTicketModel.ticket_id == event.entity_id,
                        MaintenanceTicketModel.is_verified.is_(True),
                    )
                    .values(
                        embedding_text=text,
                        index_status="INDEXED",
                        index_error_code=None,
                        indexed_at=now,
                        updated_at=now,
                    )
                )
        return {event.job_id: HandlerResult(IndexJobStatus.INDEXED) for event, _, _ in ordered}

    async def _case(self, event: IndexJobMessage) -> HandlerResult:
        async with self.session_factory() as session:
            case = await session.get(DiagnosisCaseModel, event.entity_id)
        if not case:
            raise PermanentIndexError("INDEX_ENTITY_NOT_FOUND")
        if str(case.case_version) != event.entity_version:
            raise StaleIndexEventError("INDEX_EVENT_STALE")
        if event.operation == IndexOperation.TOMBSTONE:
            if case.is_active or case.review_status not in {"DISABLED", "SUPERSEDED"}:
                raise StaleIndexEventError("INDEX_EVENT_STALE")
            await self.milvus.delete("case", [case.case_id])
            try:
                if self.graph.available:
                    if self.tracer:
                        with self.tracer.start_span(
                            "graph.case.tombstone",
                            trace_id=event.trace_id,
                            metadata={
                                "case_id": case.case_id,
                                "case_version": case.case_version,
                            },
                        ):
                            await self.graph.tombstone_case(case.case_id)
                    else:
                        await self.graph.tombstone_case(case.case_id)
            except Exception:
                await self._projection(
                    event, GraphProjectionStatus.DEGRADED, "GRAPH_PROJECTION_FAILED"
                )
                await self._set_case_index(event.entity_id, "TOMBSTONED", active=False)
                return HandlerResult(IndexJobStatus.TOMBSTONED, graph_degraded=True)
            await self._projection(event, GraphProjectionStatus.TOMBSTONED)
            await self._set_case_index(event.entity_id, "TOMBSTONED", active=False)
            return HandlerResult(IndexJobStatus.TOMBSTONED)
        if case.review_status != "APPROVED":
            raise StaleIndexEventError("INDEX_EVENT_STALE")
        text = case.embedding_text or "\n".join(
            str(value)
            for value in (
                case.device_type,
                case.device_model,
                case.alarm_name,
                case.symptom_summary,
                case.timeseries_features,
                case.root_cause,
                "；".join(case.resolution_steps),
            )
            if value
        )
        vector = (await self.embedding.embed([text]))[0]
        await self.milvus.upsert(
            "case",
            [
                {
                    "id": case.case_id,
                    "source_id": case.case_id,
                    "device_type": case.device_type or "",
                    "device_model": case.device_model or "",
                    "manufacturer": case.manufacturer or "",
                    "alarm_name": case.alarm_name or "",
                    "case_version": case.case_version,
                    "verified": True,
                    "effective": True,
                    "index_generation": f"case-v{case.case_version}",
                    "embedding": vector,
                }
            ],
        )
        graph_degraded = False
        try:
            if self.graph.available:
                if self.tracer:
                    with self.tracer.start_span(
                        "graph.case.upsert",
                        trace_id=event.trace_id,
                        metadata={
                            "case_id": case.case_id,
                            "case_version": case.case_version,
                        },
                    ):
                        await self._project_case_graph(case)
                else:
                    await self._project_case_graph(case)
                await self._projection(event, GraphProjectionStatus.PROJECTED)
            else:
                await self._projection(event, GraphProjectionStatus.DEGRADED, "GRAPH_DISABLED")
                graph_degraded = True
        except Exception:
            await self._projection(event, GraphProjectionStatus.DEGRADED, "GRAPH_PROJECTION_FAILED")
            graph_degraded = True
        await self._set_case_index(
            event.entity_id,
            "DEGRADED" if graph_degraded else "INDEXED",
            active=True,
            embedding_text=text,
        )
        if case.supersedes_case_id:
            await self._queue_superseded_case(event, case.supersedes_case_id)
        return HandlerResult(
            IndexJobStatus.DEGRADED if graph_degraded else IndexJobStatus.INDEXED,
            graph_degraded=graph_degraded,
        )

    async def _case_batch(self, events: list[IndexJobMessage]) -> dict[str, HandlerResult]:
        async with self.session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(DiagnosisCaseModel).where(
                            DiagnosisCaseModel.case_id.in_([event.entity_id for event in events])
                        )
                    )
                )
                .scalars()
                .all()
            )
        cases = {row.case_id: row for row in rows}
        ordered: list[tuple[IndexJobMessage, DiagnosisCaseModel, str]] = []
        for event in events:
            case = cases.get(event.entity_id)
            if not case:
                raise PermanentIndexError("INDEX_ENTITY_NOT_FOUND")
            if str(case.case_version) != event.entity_version or case.review_status != "APPROVED":
                raise StaleIndexEventError("INDEX_EVENT_STALE")
            text = case.embedding_text or "\n".join(
                str(value)
                for value in (
                    case.device_type,
                    case.device_model,
                    case.alarm_name,
                    case.symptom_summary,
                    case.timeseries_features,
                    case.root_cause,
                    "；".join(case.resolution_steps),
                )
                if value
            )
            ordered.append((event, case, text))
        vectors = await self.embedding.embed([item[2] for item in ordered])
        await self.milvus.upsert(
            "case",
            [
                {
                    "id": case.case_id,
                    "source_id": case.case_id,
                    "device_type": case.device_type or "",
                    "device_model": case.device_model or "",
                    "manufacturer": case.manufacturer or "",
                    "alarm_name": case.alarm_name or "",
                    "case_version": case.case_version,
                    "verified": True,
                    "effective": True,
                    "index_generation": f"case-v{case.case_version}",
                    "embedding": vector,
                }
                for (_, case, _), vector in zip(ordered, vectors, strict=True)
            ],
        )
        results: dict[str, HandlerResult] = {}
        for event, case, text in ordered:
            graph_degraded = False
            try:
                if self.graph.available:
                    await self._project_case_graph(case)
                    await self._projection(event, GraphProjectionStatus.PROJECTED)
                else:
                    await self._projection(event, GraphProjectionStatus.DEGRADED, "GRAPH_DISABLED")
                    graph_degraded = True
            except Exception:
                await self._projection(
                    event, GraphProjectionStatus.DEGRADED, "GRAPH_PROJECTION_FAILED"
                )
                graph_degraded = True
            await self._set_case_index(
                event.entity_id,
                "DEGRADED" if graph_degraded else "INDEXED",
                active=True,
                embedding_text=text,
            )
            results[event.job_id] = HandlerResult(
                IndexJobStatus.DEGRADED if graph_degraded else IndexJobStatus.INDEXED,
                graph_degraded=graph_degraded,
            )
        return results

    async def _project_case_graph(self, case: DiagnosisCaseModel) -> None:
        if not self.graph.available:
            raise RuntimeError("GRAPH_DISABLED")
        device_type = (case.device_type or "").strip()
        alarm_name = (case.alarm_name or "").strip()
        resolution_action = next(
            (str(step).strip() for step in reversed(case.resolution_steps) if str(step).strip()),
            "",
        )
        if not device_type or not alarm_name or not resolution_action:
            raise ValueError("CASE_GRAPH_FIELDS_REQUIRED")
        await self.graph.project_case(
            case_id=case.case_id,
            case_version=case.case_version,
            device_type=device_type,
            alarm_name=alarm_name,
            fault_cause=case.root_cause,
            resolution_action=resolution_action,
        )

    async def _queue_superseded_case(self, event: IndexJobMessage, old_case_id: str) -> None:
        if not self.repository:
            raise PermanentIndexError("INDEX_REPOSITORY_UNAVAILABLE")
        async with self.session_factory.begin() as session:
            old = await session.get(
                DiagnosisCaseModel,
                old_case_id,
                with_for_update=True,
            )
            if not old or old.review_status != "APPROVED":
                return
            old.review_status = "SUPERSEDED"
            old.is_active = False
            old.index_status = "QUEUED"
            old.updated_at = utc_now()
            await self.repository.add_job(
                session,
                IndexJobCreate(
                    entity_type=EntityType.DIAGNOSIS_CASE,
                    entity_id=old.case_id,
                    entity_version=str(old.case_version),
                    operation=IndexOperation.TOMBSTONE,
                    trace_id=event.trace_id,
                    correlation_id=event.correlation_id,
                    causation_id=event.job_id,
                    max_attempts=3,
                ),
            )

    async def _set_case_index(
        self,
        case_id: str,
        status: str,
        *,
        active: bool,
        embedding_text: str | None = None,
    ) -> None:
        values: dict[str, object] = {
            "index_status": status,
            "index_error_code": None,
            "is_active": active,
            "updated_at": utc_now(),
        }
        if embedding_text is not None:
            values["embedding_text"] = embedding_text
        async with self.session_factory.begin() as session:
            await session.execute(
                update(DiagnosisCaseModel)
                .where(DiagnosisCaseModel.case_id == case_id)
                .values(**values)
            )

    async def _projection(
        self,
        event: IndexJobMessage,
        status: GraphProjectionStatus,
        error_code: str | None = None,
    ) -> None:
        async with self.session_factory.begin() as session:
            row = (
                await session.execute(
                    select(GraphProjectionModel).where(
                        GraphProjectionModel.entity_type == event.entity_type,
                        GraphProjectionModel.entity_id == event.entity_id,
                        GraphProjectionModel.entity_version == event.entity_version,
                    )
                )
            ).scalar_one_or_none()
            if not row:
                row = GraphProjectionModel(
                    projection_id=new_id(),
                    entity_type=event.entity_type,
                    entity_id=event.entity_id,
                    entity_version=event.entity_version,
                    status=status,
                    updated_at=utc_now(),
                )
                session.add(row)
            row.status = status
            row.last_error_code = error_code
            row.projected_at = (
                utc_now()
                if status in {GraphProjectionStatus.PROJECTED, GraphProjectionStatus.TOMBSTONED}
                else None
            )
            row.updated_at = utc_now()
