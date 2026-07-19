from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from energy_agent.contracts.common import StrictModel


class IndexStatus(StrEnum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    INDEXED = "INDEXED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    TOMBSTONED = "TOMBSTONED"


class IndexJobStatus(StrEnum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    INDEXED = "INDEXED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    TOMBSTONED = "TOMBSTONED"
    STALE = "STALE"


class OutboxPublishStatus(StrEnum):
    PENDING = "PENDING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


class EntityType(StrEnum):
    MANUAL_DOCUMENT = "manual_document"
    MAINTENANCE_TICKET = "maintenance_ticket"
    DIAGNOSIS_CASE = "diagnosis_case"
    TEMPLATE_GRAPH = "template_graph"


class IndexOperation(StrEnum):
    UPSERT = "upsert"
    REINDEX = "reindex"
    TOMBSTONE = "tombstone"
    GRAPH_PROJECT = "graph_project"


class IndexJobMessage(StrictModel):
    schema_version: int = Field(default=1, ge=1, le=1)
    job_id: str
    entity_type: EntityType
    entity_id: str
    entity_version: str
    operation: IndexOperation
    trace_id: str
    correlation_id: str
    causation_id: str
    requested_at: datetime


class IndexJobCreate(StrictModel):
    entity_type: EntityType
    entity_id: str
    entity_version: str
    operation: IndexOperation
    trace_id: str
    correlation_id: str
    causation_id: str
    max_attempts: int = Field(default=3, ge=1, le=20)

    @property
    def idempotency_key(self) -> tuple[str, str, str, str]:
        return (
            self.entity_type,
            self.entity_id,
            self.entity_version,
            self.operation,
        )


class IndexJobRecord(IndexJobCreate):
    job_id: str
    status: IndexJobStatus
    attempt_count: int
    last_error_code: str | None = None
    last_error_message: str | None = None
    next_attempt_at: datetime | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime

    @model_validator(mode="after")
    def validate_attempts(self) -> "IndexJobRecord":
        if self.attempt_count > self.max_attempts:
            raise ValueError("attempt_count cannot exceed max_attempts")
        return self


def should_dead_letter(attempt_count: int, max_attempts: int, *, retryable: bool) -> bool:
    return not retryable or attempt_count >= max_attempts
