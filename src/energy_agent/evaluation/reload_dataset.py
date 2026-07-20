import argparse
import asyncio
import gzip
import hashlib
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from influxdb_client.client.influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncEngine

from energy_agent.core.config import Settings
from energy_agent.indexing.contracts import (
    EntityType,
    IndexJobCreate,
    IndexOperation,
)
from energy_agent.indexing.repository import IndexRepository
from energy_agent.persistence.models import (
    AlarmEventModel,
    AuditEventModel,
    CaseReviewEventModel,
    DeviceProfileModel,
    DiagnosisCaseModel,
    DiagnosisResultModel,
    DiagnosisReviewModel,
    DiagnosisRunModel,
    DiagnosisSessionModel,
    MaintenanceTicketModel,
    ManualChunkModel,
    ManualDocumentModel,
)
from energy_agent.persistence.mysql import create_mysql_engine, create_session_factory
from energy_agent.providers.minio import MinioDocumentProvider

DATASET_ID = "pilot_medium_v1"
DATASET_VERSION = "1.3.0"
DEFAULT_ROOT = Path(f"artifacts/synthetic-data/{DATASET_ID}-{DATASET_VERSION}")

BUSINESS_TABLES = (
    "diagnosis_alarm_dedup",
    "diagnosis_step_log",
    "graph_projection",
    "index_outbox",
    "index_job",
    "audit_event",
    "case_review_event",
    "diagnosis_case",
    "diagnosis_review",
    "diagnosis_result",
    "diagnosis_run",
    "diagnosis_session",
    "manual_chunk",
    "manual_document",
    "maintenance_ticket",
    "alarm_event",
    "device_profile",
)


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(UTC).replace(tzinfo=None)


def _batches(rows: list[dict[str, Any]], size: int = 1000) -> Iterable[list[dict[str, Any]]]:
    for offset in range(0, len(rows), size):
        yield rows[offset : offset + size]


async def _insert_rows(
    engine: AsyncEngine,
    model: type[Any],
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        return
    async with engine.begin() as connection:
        for batch in _batches(rows):
            await connection.execute(insert(model), batch)


def _ticket_text(row: dict[str, Any]) -> str:
    return " ".join(
        str(row.get(name, ""))
        for name in (
            "device_model",
            "alarm_name",
            "fault_symptom",
            "root_cause_text",
            "action_taken",
        )
        if row.get(name)
    )


async def reload_mysql(root: Path, settings: Settings) -> dict[str, int]:
    source = root / "mysql"
    engine = create_mysql_engine(settings.mysql_dsn)
    counts: dict[str, int] = {}
    try:
        async with engine.begin() as connection:
            await connection.execute(text("SET FOREIGN_KEY_CHECKS=0"))
            for table in BUSINESS_TABLES:
                await connection.execute(text(f"TRUNCATE TABLE `{table}`"))
            await connection.execute(text("SET FOREIGN_KEY_CHECKS=1"))

        devices = _rows(source / "devices.jsonl")
        device_rows = [
            {
                "device_id": row["device_id"],
                "site_id": row["site_id"],
                "device_type": row["device_type"],
                "device_model": row["device_model"],
                "manufacturer": row["manufacturer"],
                "commission_time": _dt(row.get("commission_time")),
                "location": row.get("location"),
                "status": row["status"],
                "rated_power": row.get("rated_power"),
            }
            for row in devices
        ]
        await _insert_rows(engine, DeviceProfileModel, device_rows)
        counts["devices"] = len(device_rows)

        alarms = _rows(source / "alarms.jsonl")
        alarm_rows = [
            {
                "alarm_id": row["alarm_id"],
                "device_id": row["device_id"],
                "site_id": row["site_id"],
                "alarm_name": row["alarm_name"],
                "alarm_level": row["alarm_level"],
                "trigger_time": _dt(row["trigger_time"]),
                "status": row["status"],
                "source_system": row["source_system"],
            }
            for row in alarms
        ]
        await _insert_rows(engine, AlarmEventModel, alarm_rows)
        counts["alarms"] = len(alarm_rows)

        tickets = _rows(source / "tickets.jsonl")
        ticket_rows = [
            {
                "ticket_id": row["ticket_id"],
                "site_id": row["site_id"],
                "device_id": row["device_id"],
                "device_model": row["device_model"],
                "alarm_name": row["alarm_name"],
                "fault_symptom": row["fault_symptom"],
                "root_cause": row["root_cause_text"],
                "action_taken": row["action_taken"],
                "is_verified": row["is_verified"],
                "close_time": _dt(row.get("close_time")),
                "manufacturer": row.get("manufacturer"),
                "embedding_text": _ticket_text(row),
                "index_status": "QUEUED" if row["is_verified"] else "PENDING",
                "index_generation": DATASET_VERSION if row["is_verified"] else None,
                "embedding_model": settings.embedding_model if row["is_verified"] else None,
                "embedding_dimension": (
                    settings.embedding_dimension if row["is_verified"] else None
                ),
                "updated_at": _dt(row.get("close_time")) or datetime.now(UTC).replace(tzinfo=None),
            }
            for row in tickets
        ]
        await _insert_rows(engine, MaintenanceTicketModel, ticket_rows)
        counts["tickets"] = len(ticket_rows)

        sessions = _rows(source / "diagnosis_sessions.jsonl")
        session_rows = [
            {
                "id": row["id"],
                "source": row["source"],
                "site_id": None,
                "device_id": None,
                "alarm_id": None,
                "alarm_name": row.get("alarm_name"),
                "phase": row["phase"],
                "final_summary": row.get("final_summary"),
                "risk_level": row["risk_level"],
                "trace_id": row["trace_id"],
                "run_id": row["run_id"],
                "created_by": row.get("created_by"),
                "latest_review_status": row.get("latest_review_status"),
                "created_at": _dt(row["created_at"]),
                "updated_at": _dt(row["updated_at"]),
            }
            for row in sessions
        ]
        await _insert_rows(engine, DiagnosisSessionModel, session_rows)
        counts["diagnosis_sessions"] = len(session_rows)

        runs = _rows(source / "diagnosis_runs.jsonl")
        run_rows = [
            {
                "id": row["id"],
                "session_id": row["session_id"],
                "trace_id": row["trace_id"],
                "idempotency_key": row.get("idempotency_key"),
                "request_hash": row["request_hash"],
                "phase": row["phase"],
                "status": row["status"],
                "started_at": _dt(row["started_at"]),
                "ended_at": _dt(row.get("ended_at")),
                "created_at": _dt(row["created_at"]),
                "updated_at": _dt(row["updated_at"]),
                "parent_run_id": None,
                "run_type": row.get("run_type", "diagnosis"),
                "diagnosis_template_id": None,
                "diagnosis_template_version": row.get("diagnosis_template_version"),
                "alarm_category": None,
                "first_event_at": None,
                "guardrail_status": None,
                "failure_category": None,
            }
            for row in runs
        ]
        await _insert_rows(engine, DiagnosisRunModel, run_rows)
        counts["diagnosis_runs"] = len(run_rows)

        result_rows = []
        for row in runs:
            result = row["diagnosis_result"]
            created = _dt(row["created_at"])
            result_rows.append(
                {
                    "run_id": row["id"],
                    "session_id": row["session_id"],
                    "summary": result["summary"],
                    "candidate_causes": result.get("candidate_causes", []),
                    "evidence": result.get("evidence", []),
                    "inspection_steps": result.get("inspection_steps", []),
                    "safety_notes": result.get("safety_notes", []),
                    "missing_information": [],
                    "recommend_ticket": False,
                    "risk_level": "medium",
                    "warnings": [],
                    "degraded_components": [],
                    "recommended_actions": [],
                    "guardrail_decision": None,
                    "created_at": created,
                    "updated_at": _dt(row["updated_at"]),
                }
            )
        await _insert_rows(engine, DiagnosisResultModel, result_rows)
        counts["diagnosis_results"] = len(result_rows)

        reviews = _rows(source / "diagnosis_reviews.jsonl")
        review_rows = [
            {
                "review_id": row["review_id"],
                "session_id": row["session_id"],
                "run_id": row["run_id"],
                "actor_id": row["actor_id"],
                "actor_role": row["actor_role"],
                "review_result": row["review_result"],
                "root_cause": row.get("root_cause"),
                "resolution_steps": row.get("resolution_steps", []),
                "comments": row.get("comments"),
                "evidence_refs": row.get("evidence_refs", []),
                "source_ticket_id": row.get("source_ticket_id"),
                "override_reason": None,
                "requested_questions": [],
                "idempotency_key": row.get("idempotency_key"),
                "request_hash": row["request_hash"],
                "trace_id": row["trace_id"],
                "created_at": _dt(row["created_at"]),
            }
            for row in reviews
        ]
        await _insert_rows(engine, DiagnosisReviewModel, review_rows)
        counts["diagnosis_reviews"] = len(review_rows)

        cases = _rows(source / "cases.jsonl")
        case_rows = [
            {
                "case_id": row["case_id"],
                "source_session_id": row["source_session_id"],
                "source_run_id": row["source_run_id"],
                "source_review_id": row["source_review_id"],
                "source_ticket_id": row.get("source_ticket_id"),
                "device_type": row.get("device_type"),
                "device_model": row.get("device_model"),
                "manufacturer": row.get("manufacturer"),
                "alarm_name": row.get("alarm_name"),
                "symptom_summary": row.get("symptom_summary"),
                "timeseries_features": row.get("timeseries_features"),
                "root_cause": row["root_cause"],
                "resolution_steps": row.get("resolution_steps", []),
                "safety_notes": row.get("safety_notes", []),
                "evidence_refs": row.get("evidence_refs", []),
                "review_status": row["review_status"],
                "reviewer": row.get("reviewer"),
                "review_comment": row.get("review_comment"),
                "case_version": row["case_version"],
                "embedding_text": " ".join(
                    str(row.get(name, ""))
                    for name in (
                        "device_type",
                        "device_model",
                        "alarm_name",
                        "symptom_summary",
                        "timeseries_features",
                        "root_cause",
                    )
                    if row.get(name)
                ),
                "index_status": ("QUEUED" if row["review_status"] == "APPROVED" else "PENDING"),
                "index_error_code": None,
                "is_active": row["is_active"],
                "supersedes_case_id": row.get("supersedes_case_id"),
                "created_by": row["created_by"],
                "created_at": _dt(row["created_at"]),
                "updated_at": _dt(row["created_at"]),
            }
            for row in cases
        ]
        await _insert_rows(engine, DiagnosisCaseModel, case_rows)
        counts["cases"] = len(case_rows)

        case_events = _rows(source / "case_review_events.jsonl")
        case_event_rows = [
            {
                "case_id": row["case_id"],
                "actor_id": row["actor_id"],
                "actor_role": row["actor_role"],
                "action": row["action"],
                "from_status": row.get("from_status"),
                "to_status": row["to_status"],
                "comment": row.get("comment"),
                "idempotency_key": row.get("idempotency_key"),
                "request_hash": row["request_hash"],
                "trace_id": row["trace_id"],
                "created_at": _dt(row["created_at"]),
            }
            for row in case_events
        ]
        await _insert_rows(engine, CaseReviewEventModel, case_event_rows)
        counts["case_review_events"] = len(case_event_rows)

        audits = _rows(source / "audit_events.jsonl")
        audit_rows = [
            {
                "actor_id": row["actor_id"],
                "actor_role": row["actor_role"],
                "action": row["action"],
                "resource_type": row["resource_type"],
                "resource_id": row["resource_id"],
                "session_id": row.get("session_id"),
                "case_id": row.get("case_id"),
                "trace_id": row["trace_id"],
                "outcome": row["outcome"],
                "safe_snapshot": row.get("safe_snapshot", {}),
                "created_at": _dt(row["created_at"]),
            }
            for row in audits
        ]
        await _insert_rows(engine, AuditEventModel, audit_rows)
        counts["audit_events"] = len(audit_rows)

        documents = json.loads(
            (root / "source_documents" / "documents.json").read_text(encoding="utf-8")
        )
        document_lookup = {row["doc_id"]: row for row in documents}
        manufacturer_by_model = {row["device_model"]: row["manufacturer"] for row in devices}
        now = datetime.now(UTC).replace(tzinfo=None)
        document_rows = []
        for row in documents:
            generation = f"{DATASET_VERSION}:{row['source_index']:02d}"
            document_rows.append(
                {
                    "doc_id": row["doc_id"],
                    "document_name": row["document_name"],
                    "object_key": (
                        f"{DATASET_ID}/{DATASET_VERSION}/{row['doc_id']}/{row['document_name']}"
                    ),
                    "content_type": row["content_type"],
                    "file_sha256": row["source_sha256"],
                    "device_type": row["device_type"],
                    "device_model": row.get("device_model"),
                    "manufacturer": manufacturer_by_model.get(row.get("device_model")),
                    "version": row["version"],
                    "review_status": row["review_status"],
                    "effective": row["effective"],
                    "parser_version": "dataset.v1.3.0",
                    "chunking_version": "dataset.v1.3.0",
                    "embedding_model": settings.embedding_model,
                    "embedding_dimension": settings.embedding_dimension,
                    "index_status": "QUEUED" if row["effective"] else "PENDING",
                    "index_generation": generation,
                    "chunk_count": row["chunk_count"],
                    "created_at": now,
                    "updated_at": now,
                }
            )
        await _insert_rows(engine, ManualDocumentModel, document_rows)
        counts["manual_documents"] = len(document_rows)

        with gzip.open(
            root / "reports" / "manual_chunks_rebuilt.jsonl.gz",
            "rt",
            encoding="utf-8",
        ) as handle:
            chunks = [json.loads(line) for line in handle]
        chunk_rows = []
        for row in chunks:
            document = document_lookup[row["doc_id"]]
            chunk_rows.append(
                {
                    "chunk_id": row["chunk_id"],
                    "doc_id": row["doc_id"],
                    "device_type": document["device_type"],
                    "device_model": row.get("device_model"),
                    "manufacturer": manufacturer_by_model.get(row.get("device_model")),
                    "alarm_name": document.get("alarm_name"),
                    "chapter_title": row["chapter_title"],
                    "page_no": row.get("page_no"),
                    "section_type": row["section_type"],
                    "summary_or_content": row["content"],
                    "version": row["version"],
                    "verified": row["review_status"] == "APPROVED",
                    "effective": row["effective"],
                    "content_hash": row["content_hash"],
                    "chunk_order": row["chunk_order"],
                    "keywords": [],
                    "embedding_text": f"{row['chapter_title']}\n{row['content']}",
                    "index_generation": (f"{DATASET_VERSION}:{document['source_index']:02d}"),
                    "embedding_model": settings.embedding_model,
                    "embedding_dimension": settings.embedding_dimension,
                    "created_at": now,
                    "updated_at": now,
                }
            )
        await _insert_rows(engine, ManualChunkModel, chunk_rows)
        counts["manual_chunks"] = len(chunk_rows)

        repository = IndexRepository(create_session_factory(engine))
        queued = 0
        async with repository.session_factory.begin() as session:
            for row in document_rows:
                if not row["effective"]:
                    continue
                await repository.add_job(
                    session,
                    IndexJobCreate(
                        entity_type=EntityType.MANUAL_DOCUMENT,
                        entity_id=str(row["doc_id"]),
                        entity_version=str(row["index_generation"]),
                        operation=IndexOperation.UPSERT,
                        trace_id=f"reload-manual-{row['doc_id']}",
                        correlation_id=str(row["doc_id"]),
                        causation_id=str(row["doc_id"]),
                        max_attempts=settings.index_max_attempts,
                    ),
                )
                queued += 1
            for row in ticket_rows:
                if not row["is_verified"]:
                    continue
                await repository.add_job(
                    session,
                    IndexJobCreate(
                        entity_type=EntityType.MAINTENANCE_TICKET,
                        entity_id=str(row["ticket_id"]),
                        entity_version=DATASET_VERSION,
                        operation=IndexOperation.UPSERT,
                        trace_id=f"reload-ticket-{row['ticket_id']}",
                        correlation_id=str(row["ticket_id"]),
                        causation_id=str(row["ticket_id"]),
                        max_attempts=settings.index_max_attempts,
                    ),
                )
                queued += 1
            for row in case_rows:
                if row["review_status"] != "APPROVED":
                    continue
                await repository.add_job(
                    session,
                    IndexJobCreate(
                        entity_type=EntityType.DIAGNOSIS_CASE,
                        entity_id=str(row["case_id"]),
                        entity_version=str(row["case_version"]),
                        operation=IndexOperation.UPSERT,
                        trace_id=f"reload-case-{row['case_id']}",
                        correlation_id=str(row["source_session_id"]),
                        causation_id=str(row["source_review_id"]),
                        max_attempts=settings.index_max_attempts,
                    ),
                )
                queued += 1
        counts["index_jobs"] = queued
        return counts
    finally:
        await engine.dispose()


async def reload_minio(root: Path, settings: Settings) -> int:
    provider = MinioDocumentProvider(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        bucket=settings.minio_bucket_documents,
        secure=settings.minio_secure,
    )
    await provider.ensure_bucket()
    old_objects = await asyncio.to_thread(
        lambda: list(
            provider.client.list_objects(
                provider.bucket,
                prefix=f"{DATASET_ID}/",
                recursive=True,
            )
        )
    )
    for old_object in old_objects:
        await asyncio.to_thread(
            provider.client.remove_object,
            provider.bucket,
            old_object.object_name,
        )
    documents = json.loads(
        (root / "source_documents" / "documents.json").read_text(encoding="utf-8")
    )
    for row in documents:
        path = root / "source_documents" / row["document_name"]
        object_key = f"{DATASET_ID}/{DATASET_VERSION}/{row['doc_id']}/{row['document_name']}"
        await provider.put_verified(
            object_key,
            path.read_bytes(),
            row["content_type"],
            {"document-id": row["doc_id"], "version": row["version"]},
        )
    return len(documents)


def reload_influx(root: Path, settings: Settings) -> int:
    path = root / "influx" / "all" / "2026-06" / "metrics.lp.gz"
    client = InfluxDBClient(
        url=settings.influxdb_url,
        token=settings.influxdb_token,
        org=settings.influxdb_org,
        timeout=60_000,
    )
    written = 0
    try:
        client.delete_api().delete(
            "2020-01-01T00:00:00Z",
            "2030-01-01T00:00:00Z",
            f'dataset_id="{DATASET_ID}"',
            bucket=settings.influxdb_bucket,
            org=settings.influxdb_org,
        )
        writer = client.write_api(write_options=SYNCHRONOUS)
        batch: list[str] = []
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                batch.append(line.rstrip())
                if len(batch) >= 10_000:
                    writer.write(
                        bucket=settings.influxdb_bucket,
                        org=settings.influxdb_org,
                        record=batch,
                    )
                    written += len(batch)
                    batch.clear()
            if batch:
                writer.write(
                    bucket=settings.influxdb_bucket,
                    org=settings.influxdb_org,
                    record=batch,
                )
                written += len(batch)
        writer.close()  # type: ignore[no-untyped-call]
        return written
    finally:
        client.close()  # type: ignore[no-untyped-call]


async def reload_dataset(root: Path, settings: Settings) -> dict[str, object]:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest["dataset_id"] != DATASET_ID or manifest["dataset_version"] != DATASET_VERSION:
        raise ValueError("DATASET_ID_OR_VERSION_MISMATCH")
    checksums = json.loads((root / "checksums.json").read_text(encoding="utf-8"))
    for relative, expected in checksums.items():
        actual = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"DATASET_CHECKSUM_MISMATCH:{relative}")
    mysql = await reload_mysql(root, settings)
    documents = await reload_minio(root, settings)
    influx_points = await asyncio.to_thread(reload_influx, root, settings)
    return {
        "dataset_id": DATASET_ID,
        "dataset_version": DATASET_VERSION,
        "mysql": mysql,
        "minio_documents": documents,
        "influx_points": influx_points,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--replace-all", action="store_true")
    args = parser.parse_args()
    if not args.replace_all:
        raise SystemExit("--replace-all is required because this operation clears business data")
    result = asyncio.run(reload_dataset(args.root, Settings()))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
