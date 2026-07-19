from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from energy_agent.core.ids import new_id
from energy_agent.core.time import ensure_utc, utc_now
from energy_agent.indexing.contracts import (
    IndexJobCreate,
    IndexJobMessage,
    IndexJobRecord,
    IndexJobStatus,
    OutboxPublishStatus,
)
from energy_agent.observability.tracing import Tracer
from energy_agent.persistence.models import (
    DiagnosisCaseModel,
    IndexJobModel,
    IndexOutboxModel,
    MaintenanceTicketModel,
    ManualDocumentModel,
)


def _record(model: IndexJobModel) -> IndexJobRecord:
    return IndexJobRecord(
        job_id=model.job_id,
        entity_type=model.entity_type,
        entity_id=model.entity_id,
        entity_version=model.entity_version,
        operation=model.operation,
        status=model.status,
        attempt_count=model.attempt_count,
        max_attempts=model.max_attempts,
        trace_id=model.trace_id,
        correlation_id=model.correlation_id,
        causation_id=model.causation_id,
        last_error_code=model.last_error_code,
        last_error_message=model.last_error_message,
        next_attempt_at=ensure_utc(model.next_attempt_at) if model.next_attempt_at else None,
        created_at=ensure_utc(model.created_at),
        started_at=ensure_utc(model.started_at) if model.started_at else None,
        finished_at=ensure_utc(model.finished_at) if model.finished_at else None,
        updated_at=ensure_utc(model.updated_at),
    )


class IndexRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        tracer: Tracer | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.tracer = tracer

    async def create_job(self, request: IndexJobCreate) -> IndexJobRecord:
        async with self.session_factory.begin() as session:
            return await self.add_job(session, request)

    async def add_job(self, session: AsyncSession, request: IndexJobCreate) -> IndexJobRecord:
        if self.tracer:
            with self.tracer.start_span(
                "index.job.create",
                trace_id=request.trace_id,
                metadata={
                    "entity_type": request.entity_type,
                    "entity_id": request.entity_id,
                    "entity_version": request.entity_version,
                    "operation": request.operation,
                },
            ):
                return await self._add_job(session, request)
        return await self._add_job(session, request)

    async def _add_job(
        self,
        session: AsyncSession,
        request: IndexJobCreate,
    ) -> IndexJobRecord:
        existing = (
            await session.execute(
                select(IndexJobModel).where(
                    IndexJobModel.entity_type == request.entity_type,
                    IndexJobModel.entity_id == request.entity_id,
                    IndexJobModel.entity_version == request.entity_version,
                    IndexJobModel.operation == request.operation,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return _record(existing)
        now = utc_now()
        job_id = new_id()
        message = IndexJobMessage(
            job_id=job_id,
            **request.model_dump(mode="python", exclude={"max_attempts"}),
            requested_at=now,
        )
        model = IndexJobModel(
            job_id=job_id,
            **request.model_dump(mode="json"),
            status=IndexJobStatus.PENDING,
            attempt_count=0,
            created_at=now,
            updated_at=now,
        )
        session.add(model)
        outbox = IndexOutboxModel(
            job_id=job_id,
            event_type="index.job.requested.v1",
            payload=message.model_dump(mode="json"),
            publish_status=OutboxPublishStatus.PENDING,
            publish_attempts=0,
            created_at=now,
            updated_at=now,
        )
        if self.tracer:
            with self.tracer.start_span(
                "index.outbox.write",
                trace_id=request.trace_id,
                metadata={"job_id": job_id, "entity_type": request.entity_type},
            ):
                session.add(outbox)
                await session.flush()
        else:
            session.add(outbox)
        return _record(model)

    async def get(self, job_id: str, *, lock: bool = False) -> IndexJobRecord | None:
        query = select(IndexJobModel).where(IndexJobModel.job_id == job_id)
        if lock:
            query = query.with_for_update()
        async with self.session_factory() as session:
            model = (await session.execute(query)).scalar_one_or_none()
        return _record(model) if model else None

    async def pending_outbox(self, limit: int = 50) -> list[IndexOutboxModel]:
        async with self.session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(IndexOutboxModel)
                        .where(IndexOutboxModel.publish_status == OutboxPublishStatus.PENDING)
                        .order_by(IndexOutboxModel.id)
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
            return list(rows)

    async def mark_published(self, outbox_id: int, job_id: str) -> None:
        now = utc_now()
        async with self.session_factory.begin() as session:
            row = await session.get(IndexOutboxModel, outbox_id, with_for_update=True)
            job = await session.get(IndexJobModel, job_id, with_for_update=True)
            if row and row.publish_status == OutboxPublishStatus.PENDING:
                row.publish_status = OutboxPublishStatus.PUBLISHED
                row.publish_attempts += 1
                row.published_at = now
                row.updated_at = now
            if job and job.status == IndexJobStatus.PENDING:
                job.status = IndexJobStatus.QUEUED
                job.updated_at = now

    async def mark_publish_failed(self, outbox_id: int, error_code: str) -> None:
        async with self.session_factory.begin() as session:
            row = await session.get(IndexOutboxModel, outbox_id, with_for_update=True)
            if row:
                row.publish_attempts += 1
                row.last_error_code = error_code
                row.updated_at = utc_now()

    async def start(self, job_id: str) -> IndexJobRecord | None:
        now = utc_now()
        async with self.session_factory.begin() as session:
            model = await session.get(IndexJobModel, job_id, with_for_update=True)
            if not model:
                return None
            if model.status in {
                IndexJobStatus.INDEXED,
                IndexJobStatus.DEGRADED,
                IndexJobStatus.TOMBSTONED,
                IndexJobStatus.STALE,
            }:
                return _record(model)
            model.status = IndexJobStatus.RUNNING
            model.attempt_count += 1
            model.started_at = now
            model.updated_at = now
            return _record(model)

    async def finish(self, job_id: str, status: IndexJobStatus) -> None:
        async with self.session_factory.begin() as session:
            model = await session.get(IndexJobModel, job_id, with_for_update=True)
            if model:
                model.status = status
                model.finished_at = utc_now()
                model.updated_at = utc_now()
                model.last_error_code = None
                model.last_error_message = None

    async def fail(
        self,
        job_id: str,
        *,
        error_code: str,
        error_message: str,
        retry_delay_ms: int | None,
    ) -> None:
        async with self.session_factory.begin() as session:
            model = await session.get(IndexJobModel, job_id, with_for_update=True)
            if model:
                model.status = (
                    IndexJobStatus.QUEUED if retry_delay_ms is not None else IndexJobStatus.FAILED
                )
                model.last_error_code = error_code
                model.last_error_message = error_message[:512]
                model.next_attempt_at = (
                    utc_now() + timedelta(milliseconds=retry_delay_ms)
                    if retry_delay_ms is not None
                    else None
                )
                model.finished_at = None if retry_delay_ms is not None else utc_now()
                model.updated_at = utc_now()
                if retry_delay_ms is None:
                    if model.entity_type == "diagnosis_case":
                        case_entity = await session.get(DiagnosisCaseModel, model.entity_id)
                        if case_entity:
                            case_entity.index_status = "FAILED"
                            case_entity.index_error_code = error_code
                            case_entity.is_active = False
                            case_entity.updated_at = utc_now()
                    elif model.entity_type == "maintenance_ticket":
                        ticket_entity = await session.get(MaintenanceTicketModel, model.entity_id)
                        if ticket_entity:
                            ticket_entity.index_status = "FAILED"
                            ticket_entity.index_error_code = error_code
                            ticket_entity.updated_at = utc_now()
                    elif model.entity_type == "manual_document":
                        document_entity = (
                            await session.execute(
                                select(ManualDocumentModel).where(
                                    ManualDocumentModel.doc_id == model.entity_id,
                                    ManualDocumentModel.index_generation == model.entity_version,
                                )
                            )
                        ).scalar_one_or_none()
                        if document_entity:
                            document_entity.index_status = "FAILED"
                            document_entity.index_error_code = error_code
                            document_entity.updated_at = utc_now()

    async def retry(self, job_id: str, trace_id: str) -> IndexJobRecord | None:
        async with self.session_factory.begin() as session:
            model = await session.get(IndexJobModel, job_id, with_for_update=True)
            if not model or model.status != IndexJobStatus.FAILED:
                return None
            now = utc_now()
            message = IndexJobMessage(
                job_id=model.job_id,
                entity_type=model.entity_type,
                entity_id=model.entity_id,
                entity_version=model.entity_version,
                operation=model.operation,
                trace_id=trace_id,
                correlation_id=model.correlation_id,
                causation_id=model.job_id,
                requested_at=now,
            )
            session.add(
                IndexOutboxModel(
                    job_id=model.job_id,
                    event_type="index.job.retried.v1",
                    payload=message.model_dump(mode="json"),
                    publish_status=OutboxPublishStatus.PENDING,
                    publish_attempts=0,
                    created_at=now,
                    updated_at=now,
                )
            )
            model.status = IndexJobStatus.PENDING
            model.attempt_count = 0
            model.last_error_code = None
            model.last_error_message = None
            model.updated_at = now
            return _record(model)

    async def failed(self, limit: int = 100) -> list[IndexJobRecord]:
        async with self.session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(IndexJobModel)
                        .where(IndexJobModel.status == IndexJobStatus.FAILED)
                        .order_by(IndexJobModel.updated_at.desc())
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
        return [_record(row) for row in rows]
