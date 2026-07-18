import asyncio
import os
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from energy_agent.app import create_app
from energy_agent.core.config import Settings
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
    DiagnosisStepLogModel,
    MaintenanceTicketModel,
    ManualChunkModel,
    ManualDocumentModel,
)
from energy_agent.persistence.mysql import create_mysql_engine, create_session_factory

MYSQL_DSN = "mysql+asyncmy://energy:energy_dev@localhost:3306/energy_agent"
DEVICE = "PCS-PHASE4-1"
ALARM = "ALARM-PHASE4-1"
ALARM_NAME = "PCS机柜温度持续升高"
OPERATOR = {
    "X-Actor-ID": "operator-phase4",
    "X-Actor-Role": "operator",
}
REVIEWER = {
    "X-Actor-ID": "reviewer-phase4",
    "X-Actor-Role": "reviewer",
}


class _Embedding:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.01] * 1024 for _ in texts]


class _FailingEmbedding:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise ConnectionError("test embedding failure")


class _Milvus:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, object]] = {}

    async def upsert(self, source: str, rows: list[dict[str, object]]) -> None:
        assert source == "case"
        self.rows.update({str(row["id"]): row for row in rows})

    async def delete(self, source: str, ids: list[str]) -> None:
        assert source == "case"
        for item in ids:
            self.rows.pop(item, None)


async def _reset_and_seed() -> None:
    engine = create_mysql_engine(MYSQL_DSN)
    factory = create_session_factory(engine)
    async with factory.begin() as session:
        for model in (
            AuditEventModel,
            CaseReviewEventModel,
            DiagnosisCaseModel,
            DiagnosisReviewModel,
            DiagnosisResultModel,
            DiagnosisStepLogModel,
            DiagnosisRunModel,
            DiagnosisSessionModel,
            MaintenanceTicketModel,
            ManualChunkModel,
            ManualDocumentModel,
            AlarmEventModel,
            DeviceProfileModel,
        ):
            await session.execute(delete(model))
        session.add(
            DeviceProfileModel(
                device_id=DEVICE,
                site_id="SITE-04",
                device_type="PCS",
                device_model="SC5000",
                manufacturer="EnergyCo",
                status="online",
            )
        )
        session.add(
            AlarmEventModel(
                alarm_id=ALARM,
                device_id=DEVICE,
                site_id="SITE-04",
                alarm_name=ALARM_NAME,
                alarm_level="high",
                trigger_time=datetime.now(UTC).replace(tzinfo=None),
                status="active",
                source_system="ems",
            )
        )
        session.add(
            ManualDocumentModel(
                doc_id="DOC-PHASE4-1",
                document_name="Phase 4 散热维护手册",
                object_key="phase4/manual.txt",
                content_type="text/plain",
                file_sha256="a" * 64,
                device_type="PCS",
                device_model="SC5000",
                manufacturer="EnergyCo",
                version="1.0",
                review_status="APPROVED",
                effective=True,
                parser_version="test",
                chunking_version="test",
                embedding_model="BAAI/bge-m3",
                embedding_dimension=1024,
                index_status="INDEXED",
                index_generation="phase4-live",
                chunk_count=1,
                created_at=datetime.now(UTC).replace(tzinfo=None),
                updated_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
        session.add(
            ManualChunkModel(
                chunk_id="CHUNK-PHASE4-1",
                doc_id="DOC-PHASE4-1",
                device_type="PCS",
                device_model="SC5000",
                manufacturer="EnergyCo",
                alarm_name=ALARM_NAME,
                chapter_title="散热系统维护",
                page_no=12,
                section_type="维护步骤",
                summary_or_content="温度升高时检查散热风扇、滤网和风道。",
                version="1.0",
                verified=True,
                effective=True,
            )
        )
    await engine.dispose()


async def _database_readback(session_id: str, case_id: str) -> dict[str, object]:
    engine = create_mysql_engine(MYSQL_DSN)
    factory = create_session_factory(engine)
    async with factory() as session:
        runs = (
            (
                await session.execute(
                    select(DiagnosisRunModel)
                    .where(DiagnosisRunModel.session_id == session_id)
                    .order_by(DiagnosisRunModel.created_at)
                )
            )
            .scalars()
            .all()
        )
        case = await session.get(DiagnosisCaseModel, case_id)
        events = (
            (
                await session.execute(
                    select(CaseReviewEventModel).where(CaseReviewEventModel.case_id == case_id)
                )
            )
            .scalars()
            .all()
        )
        audits = (
            (
                await session.execute(
                    select(AuditEventModel).where(AuditEventModel.case_id == case_id)
                )
            )
            .scalars()
            .all()
        )
    await engine.dispose()
    return {"runs": runs, "case": case, "events": events, "audits": audits}


@pytest.fixture
def phase4_data() -> None:
    asyncio.run(_reset_and_seed())
    yield
    asyncio.run(_reset_and_seed())


def _create(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/v1/diagnosis/sessions",
        headers=OPERATOR,
        json={
            "source": "alarm",
            "site_id": "SITE-04",
            "device_id": DEVICE,
            "alarm_id": ALARM,
            "alarm_name": ALARM_NAME,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.integration
def test_clarification_restore_validation_and_explanation(phase4_data: None) -> None:
    with TestClient(create_app(Settings(app_env="test"))) as client:
        created = _create(client)
        first_response = client.post(
            "/api/v1/diagnosis/chat",
            headers=OPERATOR,
            json={"session_id": created["session_id"], "message": "诊断温度告警"},
        )
        assert first_response.status_code == 200, first_response.text
        first = first_response.json()
        assert first["phase"] == "NEED_USER_INPUT"
        assert first["memory_revision"] == 2
        question = first["clarification_questions"][0]["question_id"]

        stale = client.post(
            f"/api/v1/diagnosis/sessions/{created['session_id']}/messages",
            headers=OPERATOR,
            json={
                "message": "现场反馈",
                "followup_mode": "answer_clarification",
                "expected_memory_revision": 0,
                "clarification_answers": [{"question_id": question, "answer": "现场确认风扇不转"}],
            },
        )
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "CLARIFICATION_STALE"
        unknown = client.post(
            f"/api/v1/diagnosis/sessions/{created['session_id']}/messages",
            headers=OPERATOR,
            json={
                "message": "现场反馈",
                "followup_mode": "answer_clarification",
                "expected_memory_revision": first["memory_revision"],
                "clarification_answers": [{"question_id": "unknown", "answer": "风扇不转"}],
            },
        )
        assert unknown.status_code == 422
        assert unknown.json()["error"]["code"] == "UNKNOWN_CLARIFICATION_QUESTION"
        followup = client.post(
            f"/api/v1/diagnosis/sessions/{created['session_id']}/messages",
            headers=OPERATOR,
            json={
                "message": "现场反馈",
                "followup_mode": "answer_clarification",
                "expected_memory_revision": first["memory_revision"],
                "clarification_answers": [
                    {"question_id": question, "answer": "现场确认风扇不转，滤网积尘"}
                ],
            },
        )
        assert followup.status_code == 200, followup.text
        completed = followup.json()
        assert completed["phase"] == "COMPLETED"
        assert completed["memory_revision"] == 3
        assert set(first["evidence_refs"]) <= set(completed["evidence_refs"])
        assert completed["tool_summaries"] == first["tool_summaries"]

        explanation = client.post(
            f"/api/v1/diagnosis/sessions/{created['session_id']}/messages",
            headers=OPERATOR,
            json={
                "message": "为什么这样判断",
                "followup_mode": "explain_previous_result",
            },
        )
        assert explanation.status_code == 200, explanation.text
        explained = explanation.json()
        assert explained["run_id"] != completed["run_id"]
        assert explained["evidence_refs"] == completed["evidence_refs"]

        readback = asyncio.run(_database_readback(str(created["session_id"]), "missing"))
        assert readback["runs"][-1].run_type == "explanation"
        assert readback["runs"][-1].parent_run_id == completed["run_id"]


@pytest.mark.integration
def test_roles_review_case_index_retrieval_disable_and_audit(phase4_data: None) -> None:
    with TestClient(create_app(Settings(app_env="test"))) as client:
        live = os.getenv("PHASE4_LIVE") == "1"
        if not live:
            client.app.state.embedding_provider = _Embedding()
            client.app.state.milvus_provider = _Milvus()
        milvus = client.app.state.milvus_provider
        forbidden = client.post(
            "/api/v1/diagnosis/sessions",
            headers={"X-Actor-ID": "viewer-1", "X-Actor-Role": "viewer"},
            json={
                "source": "alarm",
                "site_id": "SITE-04",
                "device_id": DEVICE,
                "alarm_id": ALARM,
            },
        )
        assert forbidden.status_code == 403
        created = _create(client)
        first = client.post(
            "/api/v1/diagnosis/chat",
            headers=OPERATOR,
            json={"session_id": created["session_id"], "message": "诊断温度告警"},
        ).json()
        question = first["clarification_questions"][0]["question_id"]
        diagnosis = client.post(
            f"/api/v1/diagnosis/sessions/{created['session_id']}/messages",
            headers=OPERATOR,
            json={
                "message": "现场检查",
                "followup_mode": "answer_clarification",
                "expected_memory_revision": first["memory_revision"],
                "clarification_answers": [{"question_id": question, "answer": "现场确认风扇不转"}],
            },
        ).json()
        root_cause = diagnosis["result"]["candidate_causes"][0]["cause"]
        evidence_ref = diagnosis["result"]["candidate_causes"][0]["supporting_evidence"][0]
        review = client.post(
            f"/api/v1/diagnosis/sessions/{created['session_id']}/review",
            headers={**OPERATOR, "Idempotency-Key": "review-phase4"},
            json={
                "review_result": "confirmed",
                "root_cause": root_cause,
                "resolution_steps": ["授权断电后更换风扇"],
                "comments": "现场已确认",
                "evidence_refs": [evidence_ref],
            },
        )
        assert review.status_code == 200, review.text
        review_body = review.json()
        assert review_body["case_status"] == "DRAFT"
        case_id = review_body["case_id"]
        submitted = client.post(
            f"/api/v1/cases/{case_id}/submit",
            headers={**OPERATOR, "Idempotency-Key": "submit-phase4"},
        )
        assert submitted.status_code == 200, submitted.text
        assert submitted.json()["review_status"] == "PENDING_REVIEW"
        self_review = client.post(
            f"/api/v1/cases/{case_id}/review",
            headers={**OPERATOR, "Idempotency-Key": "self-review"},
            json={"decision": "approve"},
        )
        assert self_review.status_code == 403
        operator_review = client.post(
            f"/api/v1/cases/{case_id}/review",
            headers={**OPERATOR, "Idempotency-Key": "operator-review"},
            json={"decision": "approve"},
        )
        assert operator_review.status_code == 403
        if not live:
            client.app.state.embedding_provider = _FailingEmbedding()
        approved = client.post(
            f"/api/v1/cases/{case_id}/review",
            headers={**REVIEWER, "Idempotency-Key": "approve-phase4"},
            json={"decision": "approve", "comment": "内容完整"},
        )
        assert approved.status_code == 200, approved.text
        approved_body = approved.json()
        assert approved_body["review_status"] == "APPROVED"
        if not live:
            assert approved_body["index_status"] == "FAILED"
            assert approved_body["is_active"] is False
            client.app.state.embedding_provider = _Embedding()
            reindexed = client.post(
                f"/api/v1/cases/{case_id}/reindex",
                headers={**REVIEWER, "Idempotency-Key": "reindex-phase4"},
            )
            assert reindexed.status_code == 200, reindexed.text
            approved_body = reindexed.json()
        assert approved_body["index_status"] == "INDEXED"
        assert approved_body["is_active"] is True
        if not live:
            assert case_id in milvus.rows

        second = _create(client)
        second_response = client.post(
            "/api/v1/diagnosis/chat",
            headers=OPERATOR,
            json={"session_id": second["session_id"], "message": "风扇不转温度升高"},
        ).json()
        second_question = second_response["clarification_questions"][0]["question_id"]
        second_result = client.post(
            f"/api/v1/diagnosis/sessions/{second['session_id']}/messages",
            headers=OPERATOR,
            json={
                "message": "现场确认",
                "followup_mode": "answer_clarification",
                "expected_memory_revision": second_response["memory_revision"],
                "clarification_answers": [
                    {"question_id": second_question, "answer": "现场确认风扇不转"}
                ],
            },
        ).json()
        assert any(
            item["source_type"] == "case" and item["citation"] == f"[案例: {case_id} v1]"
            for item in second_result["result"]["evidence"]
        )
        revision = client.post(
            f"/api/v1/cases/{case_id}/revisions",
            headers={**OPERATOR, "Idempotency-Key": "revision-phase4"},
            json={
                "symptom_summary": "机柜温度升高且风扇转速为零",
                "submit_for_review": True,
            },
        )
        assert revision.status_code == 200, revision.text
        revision_body = revision.json()
        assert revision_body["case_version"] == 2
        assert revision_body["review_status"] == "PENDING_REVIEW"
        revision_id = revision_body["case_id"]
        revision_approved = client.post(
            f"/api/v1/cases/{revision_id}/review",
            headers={**REVIEWER, "Idempotency-Key": "approve-revision-phase4"},
            json={"decision": "approve", "comment": "新版本完整"},
        )
        assert revision_approved.status_code == 200, revision_approved.text
        assert revision_approved.json()["index_status"] == "INDEXED"
        old = client.get(f"/api/v1/cases/{case_id}", headers=OPERATOR).json()
        assert old["review_status"] == "SUPERSEDED"
        assert old["index_status"] == "TOMBSTONED"
        if not live:
            assert case_id not in milvus.rows
            assert revision_id in milvus.rows
        disabled = client.post(
            f"/api/v1/cases/{revision_id}/disable",
            headers={**REVIEWER, "Idempotency-Key": "disable-phase4"},
            json={"reason": "案例已失效"},
        )
        assert disabled.status_code == 200, disabled.text
        assert disabled.json()["index_status"] == "TOMBSTONED"
        if not live:
            assert revision_id not in milvus.rows

        readback = asyncio.run(_database_readback(str(created["session_id"]), str(case_id)))
        assert readback["case"].review_status == "SUPERSEDED"
        assert len(readback["events"]) >= 4
        actions = {item.action for item in readback["audits"]}
        assert {"case.created", "case.submitted", "case.approved", "case.superseded"} <= actions
