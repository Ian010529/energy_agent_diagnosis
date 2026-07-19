from enum import StrEnum

from energy_agent.contracts.common import StrictModel


class ReviewStatus(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DISABLED = "DISABLED"


class IndexStatus(StrEnum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    INDEXED = "INDEXED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    TOMBSTONED = "TOMBSTONED"


class DocumentManifest(StrictModel):
    doc_id: str
    document_name: str
    version: str
    content_type: str
    device_type: str
    device_model: str | None = None
    manufacturer: str | None = None
    alarm_name: str | None = None
    review_status: ReviewStatus = ReviewStatus.DRAFT
    effective: bool = False


class IngestionResult(StrictModel):
    doc_id: str
    version: str
    object_key: str
    file_sha256: str
    chunk_count: int
    index_status: IndexStatus
    existing: bool = False
    job_id: str | None = None
