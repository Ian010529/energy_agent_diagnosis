from dataclasses import dataclass
from typing import Any, Protocol

from energy_agent.indexing.contracts import IndexJobCreate
from energy_agent.retrieval.ingestion.chunking import DocumentChunk
from energy_agent.retrieval.ingestion.manifests import DocumentManifest, IndexStatus


@dataclass(frozen=True, slots=True)
class ManualDocumentRecord:
    file_sha256: str
    object_key: str
    chunk_count: int
    index_status: str


class ManualDocumentPort(Protocol):
    async def find(self, doc_id: str, version: str) -> ManualDocumentRecord | None: ...

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
    ) -> str | None: ...

    async def set_index_status(
        self,
        doc_id: str,
        version: str,
        status: IndexStatus,
        *,
        error_code: str | None = None,
    ) -> None: ...


class RetrievalCandidatePort(Protocol):
    async def manual_candidates(
        self,
        filters: dict[str, object],
        *,
        effective_only: bool = True,
        strong_only: bool = False,
    ) -> list[dict[str, object]]: ...

    async def ticket_candidates(
        self, filters: dict[str, object], *, verified_only: bool = True
    ) -> list[dict[str, object]]: ...

    async def case_candidates(
        self, filters: dict[str, object], *, exclude_session_id: str | None = None
    ) -> list[dict[str, object]]: ...


class EmbeddingPort(Protocol):
    model: str
    dimension: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class VectorSearchPort(Protocol):
    async def search(
        self, source: str, vector: list[float], allowed_ids: list[str], limit: int
    ) -> list[dict[str, object]]: ...

    async def upsert(self, source: str, rows: list[dict[str, Any]]) -> None: ...


class RerankerPort(Protocol):
    async def rerank(self, query: str, candidates: list[tuple[str, str]]) -> dict[str, float]: ...


class DocumentStorePort(Protocol):
    async def put_verified(
        self,
        object_key: str,
        content: bytes,
        content_type: str,
        metadata: dict[str, str],
    ) -> str: ...
