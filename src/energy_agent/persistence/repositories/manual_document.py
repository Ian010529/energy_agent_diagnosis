from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from energy_agent.core.time import utc_now
from energy_agent.indexing.contracts import IndexJobCreate
from energy_agent.indexing.repository import IndexRepository
from energy_agent.persistence.models import ManualChunkModel, ManualDocumentModel
from energy_agent.retrieval.ingestion.chunking import DocumentChunk
from energy_agent.retrieval.ingestion.manifests import DocumentManifest, IndexStatus
from energy_agent.retrieval.ports import ManualDocumentRecord


class ManualDocumentRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        index_repository: IndexRepository | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.index_repository = index_repository

    async def find(self, doc_id: str, version: str) -> ManualDocumentRecord | None:
        async with self.session_factory() as session:
            model = (
                await session.execute(
                    select(ManualDocumentModel).where(
                        ManualDocumentModel.doc_id == doc_id,
                        ManualDocumentModel.version == version,
                    )
                )
            ).scalar_one_or_none()
        return (
            ManualDocumentRecord(
                file_sha256=model.file_sha256,
                object_key=model.object_key,
                chunk_count=model.chunk_count,
                index_status=model.index_status,
            )
            if model
            else None
        )

    async def create_pending(
        self,
        manifest: DocumentManifest,
        *,
        object_key: str,
        checksum: str,
        chunks: list[DocumentChunk],
        parser_version: str,
        chunking_version: str,
        index_generation: str,
        embedding_model: str | None,
        embedding_dimension: int | None,
        index_request: IndexJobCreate | None = None,
    ) -> str | None:
        now = utc_now()
        async with self.session_factory() as session, session.begin():
            if manifest.effective:
                await session.execute(
                    update(ManualDocumentModel)
                    .where(
                        ManualDocumentModel.doc_id == manifest.doc_id,
                        ManualDocumentModel.effective.is_(True),
                    )
                    .values(effective=False, updated_at=now)
                )
                await session.execute(
                    update(ManualChunkModel)
                    .where(
                        ManualChunkModel.doc_id == manifest.doc_id,
                        ManualChunkModel.effective.is_(True),
                    )
                    .values(effective=False, updated_at=now)
                )
            session.add(
                ManualDocumentModel(
                    doc_id=manifest.doc_id,
                    document_name=manifest.document_name,
                    object_key=object_key,
                    content_type=manifest.content_type,
                    file_sha256=checksum,
                    device_type=manifest.device_type,
                    device_model=manifest.device_model,
                    manufacturer=manifest.manufacturer,
                    version=manifest.version,
                    review_status=manifest.review_status,
                    effective=manifest.effective,
                    parser_version=parser_version,
                    chunking_version=chunking_version,
                    embedding_model=embedding_model,
                    embedding_dimension=embedding_dimension,
                    index_status=(IndexStatus.QUEUED if index_request else IndexStatus.PENDING),
                    index_generation=index_generation,
                    chunk_count=len(chunks),
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add_all(
                ManualChunkModel(
                    chunk_id=chunk.chunk_id,
                    doc_id=manifest.doc_id,
                    device_type=manifest.device_type,
                    device_model=manifest.device_model,
                    manufacturer=manifest.manufacturer,
                    alarm_name=manifest.alarm_name,
                    chapter_title=chunk.chapter_title,
                    page_no=chunk.page_no,
                    section_type=chunk.section_type,
                    summary_or_content=chunk.content,
                    version=manifest.version,
                    verified=manifest.review_status == "APPROVED",
                    effective=manifest.effective,
                    content_hash=chunk.content_hash,
                    chunk_order=chunk.chunk_order,
                    keywords=chunk.keywords,
                    embedding_text=f"{chunk.chapter_title}\n{chunk.content}",
                    index_generation=index_generation,
                    embedding_model=embedding_model,
                    embedding_dimension=embedding_dimension,
                    created_at=now,
                    updated_at=now,
                )
                for chunk in chunks
            )
            job_id: str | None = None
            if index_request:
                if not self.index_repository:
                    raise RuntimeError("index repository is unavailable")
                job = await self.index_repository.add_job(session, index_request)
                job_id = job.job_id
        return job_id

    async def set_index_status(
        self,
        doc_id: str,
        version: str,
        status: IndexStatus,
        *,
        error_code: str | None = None,
    ) -> None:
        now = utc_now()
        async with self.session_factory() as session, session.begin():
            await session.execute(
                update(ManualDocumentModel)
                .where(
                    ManualDocumentModel.doc_id == doc_id,
                    ManualDocumentModel.version == version,
                )
                .values(index_status=status, index_error_code=error_code, updated_at=now)
            )
            if status == IndexStatus.INDEXED:
                await session.execute(
                    update(ManualChunkModel)
                    .where(
                        ManualChunkModel.doc_id == doc_id,
                        ManualChunkModel.version == version,
                    )
                    .values(indexed_at=now, updated_at=now)
                )
