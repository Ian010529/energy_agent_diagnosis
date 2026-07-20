from fastapi.testclient import TestClient

from energy_agent.app import create_app
from energy_agent.contracts.common import DiagnosisPhase, RiskLevel
from energy_agent.contracts.diagnosis import (
    CreateSessionResponse,
    StructuredDiagnosisResult,
)
from energy_agent.contracts.events import SSEEvent, SSEEventType
from energy_agent.core.config import Settings
from energy_agent.core.time import utc_now
from energy_agent.guardrails.contracts import (
    GuardrailDecision,
    GuardrailStatus,
    RecommendedAction,
)


def test_recommended_action_and_guardrail_contracts() -> None:
    action = RecommendedAction(
        action_id="a1",
        description="断电检查",
        risk_level=RiskLevel.HIGH,
        requires_human_confirmation=True,
        required_role="operator",
        evidence_refs=["manual:1", "timeseries:1"],
    )
    decision = GuardrailDecision(
        status=GuardrailStatus.PASSED_WITH_WARNINGS,
        warnings=["confirmation_required"],
        requires_human_confirmation=True,
    )
    result = StructuredDiagnosisResult(
        summary="candidate",
        recommended_actions=[action],
        guardrail_decision=decision,
    )
    assert result.recommended_actions[0].execution_status == "not_executed"


def test_old_response_shape_remains_compatible() -> None:
    result = StructuredDiagnosisResult(summary="legacy")
    assert result.recommended_actions == []
    response = CreateSessionResponse(
        session_id="s",
        run_id="r",
        phase=DiagnosisPhase.INIT,
        trace_id="t",
    )
    assert response.merged is False and response.duplicate_count == 1


def test_six_event_types_and_payload_contract() -> None:
    assert {item.value for item in SSEEventType} == {
        "intent_identified",
        "data_fetch_started",
        "retrieval_completed",
        "need_user_input",
        "draft_generated",
        "completed",
    }
    event = SSEEvent(
        event=SSEEventType.COMPLETED,
        event_sequence=1,
        timestamp=utc_now(),
        session_id="s",
        run_id="r",
        trace_id="t",
        phase="COMPLETED",
        payload={},
    )
    assert event.event_sequence == 1


def test_pilot_configuration_requires_trusted_headers() -> None:
    try:
        Settings(pilot_mode=True)
    except ValueError as exc:
        assert "PILOT_MODE requires" in str(exc)
    else:
        raise AssertionError("pilot configuration should have failed")


def test_actual_request_body_size_is_enforced_when_header_is_misleading() -> None:
    settings = Settings(app_env="test", request_body_max_bytes=1024)
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/diagnosis/chat",
            content=b"x" * 2048,
            headers={
                "Content-Type": "application/json",
                "Content-Length": "1",
                "Transfer-Encoding": "chunked",
            },
        )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "REQUEST_BODY_TOO_LARGE"
