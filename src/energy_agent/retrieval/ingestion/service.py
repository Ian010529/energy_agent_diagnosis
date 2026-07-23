import hashlib
from typing import Any

from energy_agent.core.errors import (
    DocumentHashConflictError,
    DocumentParseError,
    DocumentTooLargeError,
)
from energy_agent.core.ids import new_id
from energy_agent.indexing.contracts import EntityType, IndexJobCreate, IndexOperation
from energy_agent.observability.tracing import Tracer
from energy_agent.retrieval.ingestion.chunking import CHUNKING_VERSION, chunk_blocks
from energy_agent.retrieval.ingestion.manifests import (
    DocumentManifest,
    IndexStatus,
    IngestionResult,
)
from energy_agent.retrieval.ingestion.parsers import PARSER_VERSION, parse_document
from energy_agent.retrieval.ports import (
    DocumentStorePort,
    EmbeddingPort,
    ManualDocumentPort,
    VectorSearchPort,
)


class DocumentIngestionService:
    def __init__(
        self,
        *,
        repository: ManualDocumentPort,
        minio: DocumentStorePort,
        milvus: VectorSearchPort | None,
        embedding: EmbeddingPort | None,
        tracer: Tracer,
        max_bytes: int,
        index_execution_mode: str = "sync",
        index_max_attempts: int = 3,
    ) -> None:
        self.repository = repository
        self.minio = minio
        self.milvus = milvus
        self.embedding = embedding
        self.tracer = tracer
        self.max_bytes = max_bytes
        self.index_execution_mode = index_execution_mode
        self.index_max_attempts = index_max_attempts

    async def ingest(self, manifest: DocumentManifest, content: bytes) -> IngestionResult:
        if len(content) > self.max_bytes:
            raise DocumentTooLargeError("Document exceeds configured size limit")
        checksum = hashlib.sha256(content).hexdigest()
        existing = await self.repository.find(manifest.doc_id, manifest.version)
        if existing:
            if existing.file_sha256 != checksum:
                raise DocumentHashConflictError(
                    "Document version already exists with a different hash"
                )
            return IngestionResult(
                doc_id=manifest.doc_id,
                version=manifest.version,
                object_key=existing.object_key,
                file_sha256=checksum,
                chunk_count=existing.chunk_count,
                index_status=IndexStatus(existing.index_status),
                existing=True,
            )
        object_key = f"{manifest.doc_id}/{manifest.version}/{checksum}/{manifest.document_name}"
        generation = new_id()
        trace_id = f"ingest-{generation}"
        with self.tracer.start_span(
            "retrieval.document_ingest",
            trace_id=trace_id,
            metadata={
                "doc_id": manifest.doc_id,
                "version": manifest.version,
                "content_type": manifest.content_type,
                "file_size": len(content),
            },
        ):
            await self.minio.put_verified(
                object_key,
                content,
                manifest.content_type,
                {
                    "document-id": manifest.doc_id,
                    "version": manifest.version,
                },
            )
            with self.tracer.start_span(
                "retrieval.document_parse",
                trace_id=trace_id,
                metadata={"doc_id": manifest.doc_id, "parser_version": PARSER_VERSION},
            ):
                blocks = parse_document(manifest.document_name, content)
            if not blocks:
                raise DocumentParseError("Document contains no text")
            with self.tracer.start_span(
                "retrieval.chunking",
                trace_id=trace_id,
                metadata={
                    "doc_id": manifest.doc_id,
                    "chunking_version": CHUNKING_VERSION,
                },
            ) as span:
                chunks = chunk_blocks(manifest.doc_id, manifest.version, blocks)
                span.set_output({"chunk_count": len(chunks)})
            index_request = (
                IndexJobCreate(
                    entity_type=EntityType.MANUAL_DOCUMENT,
                    entity_id=manifest.doc_id,
                    entity_version=generation,
                    operation=IndexOperation.UPSERT,
                    trace_id=trace_id,
                    correlation_id=manifest.doc_id,
                    causation_id=generation,
                    max_attempts=self.index_max_attempts,
                )
                if self.index_execution_mode == "rabbitmq"
                else None
            )
            job_id = await self.repository.create_pending(
                manifest,
                object_key=object_key,
                checksum=checksum,
                chunks=chunks,
                parser_version=PARSER_VERSION,
                chunking_version=CHUNKING_VERSION,
                index_generation=generation,
                embedding_model=self.embedding.model if self.embedding else None,
                embedding_dimension=self.embedding.dimension if self.embedding else None,
                index_request=index_request,
            )
            if index_request:
                status = IndexStatus.QUEUED
                return IngestionResult(
                    doc_id=manifest.doc_id,
                    version=manifest.version,
                    object_key=object_key,
                    file_sha256=checksum,
                    chunk_count=len(chunks),
                    index_status=status,
                    job_id=job_id,
                )
            status = IndexStatus.DEGRADED
            error_code: str | None = "EMBEDDING_UNAVAILABLE"
            if self.embedding and self.milvus:
                try:
                    with self.tracer.start_span(
                        "retrieval.embedding",
                        trace_id=trace_id,
                        metadata={"doc_id": manifest.doc_id, "chunk_count": len(chunks)},
                    ):
                        vectors = await self.embedding.embed(
                            [f"{chunk.chapter_title}\n{chunk.content}" for chunk in chunks]
                        )
                    rows: list[dict[str, Any]] = [
                        {
                            "id": chunk.chunk_id,
                            "source_id": manifest.doc_id,
                            "device_type": manifest.device_type,
                            "device_model": manifest.device_model or "",
                            "manufacturer": manifest.manufacturer or "",
                            "alarm_name": manifest.alarm_name or "",
                            "index_generation": generation,
                            "verified": manifest.review_status == "APPROVED",
                            "effective": manifest.effective,
                            "embedding": vector,
                        }
                        for chunk, vector in zip(chunks, vectors, strict=True)
                    ]
                    with self.tracer.start_span(
                        "retrieval.milvus_upsert",
                        trace_id=trace_id,
                        metadata={"doc_id": manifest.doc_id, "vector_count": len(rows)},
                    ):
                        await self.milvus.upsert("manual", rows)
                    status, error_code = IndexStatus.INDEXED, None
                except Exception as exc:
                    status, error_code = (
                        IndexStatus.FAILED,
                        getattr(exc, "code", type(exc).__name__),
                    )
            await self.repository.set_index_status(
                manifest.doc_id, manifest.version, status, error_code=error_code
            )
        return IngestionResult(
            doc_id=manifest.doc_id,
            version=manifest.version,
            object_key=object_key,
            file_sha256=checksum,
            chunk_count=len(chunks),
            index_status=status,
            job_id=None,
        )
