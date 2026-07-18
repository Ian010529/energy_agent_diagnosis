from energy_agent.app import create_app
from energy_agent.contracts.common import DiagnosisIntent
from energy_agent.tools.contracts import (
    AlarmDetailInput,
    DeviceProfileInput,
    ManualSearchInput,
    TicketSearchInput,
    TimeseriesWindowInput,
    ToolResult,
)


def test_phase2_intent_and_five_tool_schemas_are_frozen() -> None:
    assert {item.value for item in DiagnosisIntent} == {
        "fault_diagnosis",
        "knowledge_qa",
        "history_ticket_query",
        "followup_clarification",
    }
    schemas = [
        DeviceProfileInput,
        AlarmDetailInput,
        TimeseriesWindowInput,
        ManualSearchInput,
        TicketSearchInput,
    ]
    assert len(schemas) == 5
    assert all(schema.model_json_schema()["additionalProperties"] is False for schema in schemas)
    assert ToolResult.model_json_schema()["additionalProperties"] is False


def test_openapi_preserves_phase2_apis_without_ticket_write_api() -> None:
    app = create_app()
    paths = app.openapi()["paths"]
    assert "/api/v1/diagnosis/sessions" in paths
    assert "/api/v1/diagnosis/chat" in paths
    assert "/api/v1/diagnosis/sessions/{session_id}/messages" in paths
    assert "/api/v1/diagnosis/sessions/{session_id}/messages/stream" in paths
    assert "/api/v1/diagnosis/sessions/{session_id}" in paths
    assert all("ticket" not in path for path in paths)
