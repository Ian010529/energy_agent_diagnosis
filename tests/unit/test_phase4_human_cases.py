from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from energy_agent.api.auth import require_roles
from energy_agent.cases.service import build_embedding_text, missing_case_fields
from energy_agent.contracts.cases import (
    CaseIndexStatus,
    CaseStatus,
    DiagnosisCase,
    DiagnosisReviewRequest,
)
from energy_agent.core.context import ActorContext, ActorRole
from energy_agent.core.errors import PermissionDeniedError
from energy_agent.retrieval.contracts import SourceType
from energy_agent.retrieval.scoring import source_reliability
from energy_agent.tools.contracts import AppendCaseReviewInput


def _case(**updates: object) -> DiagnosisCase:
    now = datetime.now(UTC)
    values = {
        "case_id": "case-1",
        "source_session_id": "session-1",
        "source_run_id": "run-1",
        "source_review_id": "review-1",
        "device_type": "PCS",
        "device_model": "SC5000",
        "manufacturer": "EnergyCo",
        "alarm_name": "温度告警",
        "symptom_summary": "机柜温度升高",
        "timeseries_features": "温度上升且风扇转速为零",
        "root_cause": "散热风扇失效",
        "resolution_steps": ["授权断电后更换风扇"],
        "evidence_refs": ["timeseries:1"],
        "review_status": CaseStatus.DRAFT,
        "case_version": 1,
        "index_status": CaseIndexStatus.PENDING,
        "is_active": False,
        "created_by": "operator-1",
        "created_at": now,
        "updated_at": now,
    }
    values.update(updates)
    return DiagnosisCase.model_validate(values)


def test_actor_roles_and_permissions() -> None:
    actor = ActorContext("viewer-1", ActorRole.VIEWER, "development_headers")
    with pytest.raises(PermissionDeniedError):
        require_roles(actor, {ActorRole.OPERATOR})
    require_roles(
        ActorContext("operator-1", ActorRole.OPERATOR, "development_headers"),
        {ActorRole.OPERATOR},
    )


def test_review_contract_decision_rules() -> None:
    with pytest.raises(ValidationError):
        DiagnosisReviewRequest(review_result="confirmed")
    confirmed = DiagnosisReviewRequest(
        review_result="confirmed",
        root_cause="风扇失效",
        resolution_steps=["更换风扇"],
        evidence_refs=["timeseries:1"],
    )
    assert confirmed.review_result == "confirmed"


def test_case_completeness_and_embedding_text() -> None:
    case = _case()
    assert missing_case_fields(case, {"timeseries:1"}) == []
    text = build_embedding_text(case)
    assert "PCS" in text
    assert "散热风扇失效" in text
    assert "完整工单" not in text
    assert missing_case_fields(case, set()) == ["valid_evidence_refs"]


def test_case_source_is_high_trust_but_not_probability() -> None:
    assert SourceType.CASE == "case"
    assert source_reliability(SourceType.CASE, {"verified": True}) == 0.95


def test_append_case_review_requires_explicit_human_action() -> None:
    base = {
        "context": {
            "trace_id": "trace-1",
            "source_system": "test",
            "operator_id": "operator-1",
            "actor_role": "operator",
        },
        "session_id": "session-1",
        "run_id": "run-1",
        "review_id": "review-1",
        "review_result": "rejected",
        "reviewer": "operator-1",
        "request_hash": "hash",
    }
    with pytest.raises(ValidationError):
        AppendCaseReviewInput.model_validate(base)
    base["context"]["explicit_human_action"] = True
    assert AppendCaseReviewInput.model_validate(base).reviewer == "operator-1"
