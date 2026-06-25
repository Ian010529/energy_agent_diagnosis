"""验证超集契约和文档遗留字段的统一归一化。"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from energy_agent_diagnosis.contracts import (
    AlarmContext,
    DiagnosisResult,
    DiagnosisStatus,
    EvidenceItem,
    EvidencePackage,
    ProviderType,
    RequestContext,
    TicketSuggestion,
    TimeWindow,
    ToolMeta,
    ToolResult,
    ToolStatus,
)


def test_tool_result_normalizes_success_and_top_level_meta() -> None:
    result = ToolResult[dict[str, object]].model_validate(
        {
            "success": True,
            "status": "SUCCESS",
            "data": {},
            "trace_id": "trace-1",
            "source": "mock",
        }
    )

    assert result.status is ToolStatus.OK
    assert result.meta.trace_id == "trace-1"
    assert result.meta.provider_type is ProviderType.MOCK


def test_tool_result_maps_external_source_system() -> None:
    result = ToolResult[dict[str, object]].model_validate(
        {
            "success": True,
            "status": "OK",
            "data": {},
            "trace_id": "trace-1",
            "source": "ems",
        }
    )

    assert result.meta.source_system == "ems"


def test_failed_tool_result_requires_error_code() -> None:
    with pytest.raises(ValidationError):
        ToolResult[dict[str, object]](
            success=False,
            status=ToolStatus.FAILED,
            meta=ToolMeta(trace_id="trace-1"),
        )


def test_request_and_time_aliases_are_normalized() -> None:
    now = datetime.now(tz=UTC)
    request = RequestContext(
        request_id="req-1",
        trace_id="trace-1",
        session_id="session-1",
        request_source="alarm",
        alarm=AlarmContext(alarm_time=now),
    )
    window = TimeWindow(start=now, end=now)

    assert request.request_source == "alarm"
    assert request.alarm and request.alarm.trigger_time == now
    assert window.start_time == now
    assert window.end_time == now


def test_document_request_shape_is_fully_normalized() -> None:
    request = RequestContext.model_validate(
        {
            "request_id": "req-1",
            "trace_id": "trace-1",
            "session_id": "session-1",
            "source": "alarm",
            "user": {"user_id": "u1", "role": "operator"},
            "site": {"site_id": "site-1"},
            "device": {
                "device_id": "device-1",
                "device_type": "PCS",
                "device_model": "SC5000",
                "manufacturer": "vendor",
            },
            "alarm": {"alarm_time": "2026-06-23T10:30:00+08:00"},
            "message": "检查温度告警",
            "options": {"stream": True, "debug": False},
        }
    )

    assert request.user_id == "u1"
    assert request.site_id == "site-1"
    assert request.device_id == "device-1"
    assert request.manufacturer == "vendor"
    assert request.stream is True


def test_request_rejects_unknown_nested_fields_and_naive_time() -> None:
    base = {
        "request_id": "req-1",
        "trace_id": "trace-1",
        "session_id": "session-1",
        "source": "alarm",
    }
    with pytest.raises(ValidationError):
        RequestContext.model_validate({**base, "device": {"unexpected": "value"}})
    with pytest.raises(ValidationError):
        RequestContext.model_validate({**base, "alarm": {"alarm_time": "2026-06-23T10:30:00"}})


@pytest.mark.parametrize("status", list(ToolStatus))
def test_all_tool_statuses_have_consistent_success_rules(status: ToolStatus) -> None:
    successful = status in {ToolStatus.OK, ToolStatus.PARTIAL_SUCCESS}
    result = ToolResult[dict[str, object]](
        success=successful,
        status=status,
        data={},
        meta=ToolMeta(trace_id="trace-1"),
        error_code="" if successful else "EXPECTED_NON_SUCCESS",
    )

    assert result.status is status


def test_tool_result_rejects_status_mismatch_and_maps_real_source() -> None:
    result = ToolResult[dict[str, object]].model_validate(
        {
            "success": True,
            "status": "OK",
            "data": {},
            "trace_id": "trace-1",
            "source": "real",
        }
    )
    assert result.meta.provider_type is ProviderType.REAL

    with pytest.raises(ValidationError):
        ToolResult[dict[str, object]](
            success=True,
            status=ToolStatus.FAILED,
            meta=ToolMeta(trace_id="trace-1"),
        )


def test_evidence_and_diagnosis_keep_public_contract_fields() -> None:
    now = datetime.now(tz=UTC)
    evidence = EvidenceItem(
        evidence_id="ev-1",
        source_type="manual",
        source_id="manual-1",
        chunk_id="chunk-1",
        page_number=3,
        section="散热系统",
        time_window=TimeWindow(start=now, end=now),
        quote_text="检查风扇",
        score=0.9,
        verified=True,
        weak_evidence=False,
    )
    package = EvidencePackage(
        package_id="pkg-1",
        session_id="session-1",
        trace_id="trace-1",
        ranked_evidence=[evidence],
    )
    diagnosis = DiagnosisResult(
        session_id="session-1",
        status=DiagnosisStatus.DRAFT_READY,
        evidence_package_id=package.package_id,
        ticket_suggestion=TicketSuggestion(action="create", summary="检查散热系统"),
        generated_at=now,
    )

    assert package.ranked_evidence[0].chunk_id == "chunk-1"
    assert diagnosis.ticket_suggestion and diagnosis.ticket_suggestion.draft is True
