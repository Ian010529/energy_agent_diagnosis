from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from energy_agent.contracts.common import DiagnosisPhase
from energy_agent.contracts.diagnosis import DiagnosisSessionCreate, SessionMemoryPayload
from energy_agent.contracts.errors import ErrorBody, ErrorEnvelope
from energy_agent.contracts.events import SSEEventType
from energy_agent.core.ids import new_id


def test_diagnosis_phase_contract_is_complete() -> None:
    assert {phase.value for phase in DiagnosisPhase} == {
        "INIT",
        "PLAN_READY",
        "DATA_FETCHING",
        "EVIDENCE_READY",
        "NEED_USER_INPUT",
        "DRAFT_READY",
        "REVIEWING",
        "COMPLETED",
        "FAILED",
    }


def test_sse_event_contract_is_complete() -> None:
    assert {event.value for event in SSEEventType} == {
        "intent_identified",
        "data_fetch_started",
        "retrieval_completed",
        "need_user_input",
        "draft_generated",
        "completed",
    }


def test_cross_boundary_models_reject_extra_fields() -> None:
    with pytest.raises(ValidationError):
        DiagnosisSessionCreate.model_validate(
            {
                "id": new_id(),
                "source": "chat",
                "trace_id": new_id(),
                "run_id": new_id(),
                "unexpected": True,
            }
        )


def test_error_envelope_shape() -> None:
    envelope = ErrorEnvelope(
        error=ErrorBody(code="TEST", message="safe"),
        trace_id=new_id(),
    )
    assert envelope.model_dump()["error"] == {
        "code": "TEST",
        "message": "safe",
        "retryable": False,
        "details": {},
    }


def test_redis_session_payload_round_trip() -> None:
    payload = SessionMemoryPayload(
        session_id=new_id(),
        phase=DiagnosisPhase.INIT,
        run_id=new_id(),
        trace_id=new_id(),
        updated_at=datetime.now(UTC),
    )
    assert SessionMemoryPayload.model_validate_json(payload.model_dump_json()) == payload
