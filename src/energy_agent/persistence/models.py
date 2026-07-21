from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from energy_agent.persistence.mysql import Base


class DiagnosisSessionModel(Base):
    __tablename__ = "diagnosis_session"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    site_id: Mapped[str | None] = mapped_column(String(128))
    device_id: Mapped[str | None] = mapped_column(String(128))
    alarm_id: Mapped[str | None] = mapped_column(String(128))
    alarm_name: Mapped[str | None] = mapped_column(String(255))
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
    final_summary: Mapped[str | None] = mapped_column(Text)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(128))
    latest_review_status: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)


class DiagnosisStepLogModel(Base):
    __tablename__ = "diagnosis_step_log"
    __table_args__ = (Index("ix_step_log_session_id", "session_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("diagnosis_session.id"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    step_name: Mapped[str] = mapped_column(String(128), nullable=False)
    step_status: Mapped[str] = mapped_column(String(32), nullable=False)
    input_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    output_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    duration_ms: Mapped[int | None] = mapped_column(Integer)


class DiagnosisTimelineEventModel(Base):
    __tablename__ = "diagnosis_timeline_event"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_timeline_event_id"),
        UniqueConstraint("session_id", "sequence", name="uq_timeline_session_sequence"),
        Index("ix_timeline_session_sequence", "session_id", "sequence"),
        Index("ix_timeline_run_id", "run_id"),
        Index("ix_timeline_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("diagnosis_session.id"), nullable=False
    )
    run_id: Mapped[str | None] = mapped_column(String(64))
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(128))
    actor_role: Mapped[str | None] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)


class DiagnosisRunModel(Base):
    __tablename__ = "diagnosis_run"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("diagnosis_session.id"), nullable=False, index=True
    )
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    parent_run_id: Mapped[str | None] = mapped_column(String(64))
    run_type: Mapped[str] = mapped_column(String(32), nullable=False, default="diagnosis")
    diagnosis_template_id: Mapped[str | None] = mapped_column(String(128))
    diagnosis_template_version: Mapped[str | None] = mapped_column(String(32))
    alarm_category: Mapped[str | None] = mapped_column(String(64))
    first_event_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    guardrail_status: Mapped[str | None] = mapped_column(String(32))
    failure_category: Mapped[str | None] = mapped_column(String(64))


class DiagnosisResultModel(Base):
    __tablename__ = "diagnosis_result"

    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("diagnosis_run.id"), primary_key=True
    )
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("diagnosis_session.id"), nullable=False, index=True
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_causes: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    inspection_steps: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    safety_notes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    missing_information: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    recommend_ticket: Mapped[bool] = mapped_column(nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    degraded_components: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    recommended_actions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    guardrail_decision: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)


class DiagnosisAlarmDedupModel(Base):
    __tablename__ = "diagnosis_alarm_dedup"
    __table_args__ = (Index("ix_alarm_dedup_lookup", "device_id", "alarm_category", "expires_at"),)

    dedup_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(128), nullable=False)
    alarm_category: Mapped[str] = mapped_column(String(128), nullable=False)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("diagnosis_session.id"), nullable=False
    )
    alarm_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)


class DeviceProfileModel(Base):
    __tablename__ = "device_profile"

    device_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    site_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    device_type: Mapped[str] = mapped_column(String(64), nullable=False)
    device_model: Mapped[str] = mapped_column(String(128), nullable=False)
    manufacturer: Mapped[str] = mapped_column(String(128), nullable=False)
    commission_time: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    location: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    rated_power: Mapped[float | None] = mapped_column()


class AlarmEventModel(Base):
    __tablename__ = "alarm_event"

    alarm_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    site_id: Mapped[str] = mapped_column(String(128), nullable=False)
    alarm_name: Mapped[str] = mapped_column(String(255), nullable=False)
    alarm_level: Mapped[str] = mapped_column(String(32), nullable=False)
    trigger_time: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)


class ManualChunkModel(Base):
    __tablename__ = "manual_chunk"

    chunk_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    doc_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    device_type: Mapped[str] = mapped_column(String(64), nullable=False)
    device_model: Mapped[str | None] = mapped_column(String(128))
    manufacturer: Mapped[str | None] = mapped_column(String(128))
    alarm_name: Mapped[str | None] = mapped_column(String(255))
    chapter_title: Mapped[str] = mapped_column(String(255), nullable=False)
    page_no: Mapped[int | None] = mapped_column(Integer)
    section_type: Mapped[str] = mapped_column(String(64), nullable=False)
    summary_or_content: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    verified: Mapped[bool] = mapped_column(nullable=False)
    effective: Mapped[bool] = mapped_column(nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    chunk_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    keywords: Mapped[list[str] | None] = mapped_column(JSON)
    embedding_text: Mapped[str | None] = mapped_column(Text)
    index_generation: Mapped[str | None] = mapped_column(String(64))
    embedding_model: Mapped[str | None] = mapped_column(String(128))
    embedding_dimension: Mapped[int | None] = mapped_column(Integer)
    indexed_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    created_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    updated_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))


class MaintenanceTicketModel(Base):
    __tablename__ = "maintenance_ticket"

    ticket_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    site_id: Mapped[str] = mapped_column(String(128), nullable=False)
    device_id: Mapped[str] = mapped_column(String(128), nullable=False)
    device_model: Mapped[str] = mapped_column(String(128), nullable=False)
    alarm_name: Mapped[str] = mapped_column(String(255), nullable=False)
    fault_symptom: Mapped[str] = mapped_column(Text, nullable=False)
    root_cause: Mapped[str] = mapped_column(Text, nullable=False)
    action_taken: Mapped[str] = mapped_column(Text, nullable=False)
    is_verified: Mapped[bool] = mapped_column(nullable=False, index=True)
    close_time: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    manufacturer: Mapped[str | None] = mapped_column(String(128))
    embedding_text: Mapped[str | None] = mapped_column(Text)
    index_status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    index_error_code: Mapped[str | None] = mapped_column(String(64))
    index_generation: Mapped[str | None] = mapped_column(String(64))
    embedding_model: Mapped[str | None] = mapped_column(String(128))
    embedding_dimension: Mapped[int | None] = mapped_column(Integer)
    indexed_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    updated_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))


class ManualDocumentModel(Base):
    __tablename__ = "manual_document"
    __table_args__ = (UniqueConstraint("doc_id", "version", name="uq_manual_document_version"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    doc_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    document_name: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    device_type: Mapped[str] = mapped_column(String(64), nullable=False)
    device_model: Mapped[str | None] = mapped_column(String(128))
    manufacturer: Mapped[str | None] = mapped_column(String(128))
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False)
    effective: Mapped[bool] = mapped_column(nullable=False)
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False)
    chunking_version: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_model: Mapped[str | None] = mapped_column(String(128))
    embedding_dimension: Mapped[int | None] = mapped_column(Integer)
    index_status: Mapped[str] = mapped_column(String(32), nullable=False)
    index_error_code: Mapped[str | None] = mapped_column(String(64))
    index_generation: Mapped[str | None] = mapped_column(String(64))
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)


class DiagnosisReviewModel(Base):
    __tablename__ = "diagnosis_review"
    __table_args__ = (
        UniqueConstraint("session_id", "idempotency_key", name="uq_review_session_idempotency"),
    )

    review_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("diagnosis_session.id"), nullable=False, index=True
    )
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    review_result: Mapped[str] = mapped_column(String(32), nullable=False)
    root_cause: Mapped[str | None] = mapped_column(Text)
    resolution_steps: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    comments: Mapped[str | None] = mapped_column(Text)
    evidence_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    source_ticket_id: Mapped[str | None] = mapped_column(String(128))
    override_reason: Mapped[str | None] = mapped_column(Text)
    requested_questions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)


class DiagnosisCaseModel(Base):
    __tablename__ = "diagnosis_case"
    __table_args__ = (
        UniqueConstraint("source_session_id", "case_version", name="uq_case_session_version"),
        Index("ix_case_retrieval", "review_status", "index_status", "is_active"),
    )

    case_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_review_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_ticket_id: Mapped[str | None] = mapped_column(String(128))
    device_type: Mapped[str | None] = mapped_column(String(64))
    device_model: Mapped[str | None] = mapped_column(String(128))
    manufacturer: Mapped[str | None] = mapped_column(String(128))
    alarm_name: Mapped[str | None] = mapped_column(String(255))
    symptom_summary: Mapped[str | None] = mapped_column(Text)
    timeseries_features: Mapped[str | None] = mapped_column(Text)
    root_cause: Mapped[str] = mapped_column(Text, nullable=False)
    resolution_steps: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    safety_notes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    evidence_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False)
    reviewer: Mapped[str | None] = mapped_column(String(128))
    review_comment: Mapped[str | None] = mapped_column(Text)
    case_version: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_text: Mapped[str | None] = mapped_column(Text)
    index_status: Mapped[str] = mapped_column(String(32), nullable=False)
    index_error_code: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(nullable=False)
    supersedes_case_id: Mapped[str | None] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)


class CaseReviewEventModel(Base):
    __tablename__ = "case_review_event"
    __table_args__ = (
        UniqueConstraint("case_id", "idempotency_key", name="uq_case_event_idempotency"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)


class AuditEventModel(Base):
    __tablename__ = "audit_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(64), nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(64))
    case_id: Mapped[str | None] = mapped_column(String(64))
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    safe_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)


class IndexJobModel(Base):
    __tablename__ = "index_job"
    __table_args__ = (
        UniqueConstraint(
            "entity_type",
            "entity_id",
            "entity_version",
            "operation",
            name="uq_index_job_entity_operation",
        ),
        Index("ix_index_job_status_next_attempt", "status", "next_attempt_at"),
    )

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_version: Mapped[str] = mapped_column(String(64), nullable=False)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    causation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    last_error_message: Mapped[str | None] = mapped_column(String(512))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    finished_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)


class IndexOutboxModel(Base):
    __tablename__ = "index_outbox"
    __table_args__ = (Index("ix_index_outbox_publish_status", "publish_status", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("index_job.job_id"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    publish_status: Mapped[str] = mapped_column(String(32), nullable=False)
    publish_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)


class GraphProjectionModel(Base):
    __tablename__ = "graph_projection"
    __table_args__ = (
        UniqueConstraint(
            "entity_type",
            "entity_id",
            "entity_version",
            name="uq_graph_projection_entity_version",
        ),
    )

    projection_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    projected_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
