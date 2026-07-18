from energy_agent.app import create_app
from energy_agent.contracts.events import SSEEventType
from energy_agent.retrieval.contracts import EvidencePackage, SourceType
from energy_agent.tools.contracts import AppendCaseReviewInput


def test_phase4_openapi_and_legacy_paths() -> None:
    paths = create_app().openapi()["paths"]
    for path in (
        "/api/v1/diagnosis/sessions",
        "/api/v1/diagnosis/chat",
        "/api/v1/diagnosis/sessions/{session_id}/messages",
        "/api/v1/diagnosis/sessions/{session_id}/messages/stream",
        "/api/v1/diagnosis/sessions/{session_id}",
        "/api/v1/diagnosis/sessions/{session_id}/review",
        "/api/v1/cases",
        "/api/v1/cases/{case_id}",
        "/api/v1/cases/{case_id}/history",
        "/api/v1/cases/{case_id}/submit",
        "/api/v1/cases/{case_id}/review",
        "/api/v1/cases/{case_id}/disable",
        "/api/v1/cases/{case_id}/revisions",
        "/api/v1/cases/{case_id}/reindex",
    ):
        assert path in paths
    assert all("ticket" not in path for path in paths)


def test_phase4_contract_extensions_are_backward_compatible() -> None:
    assert SourceType.CASE.value == "case"
    assert "case_evidence" in EvidencePackage.model_fields
    schema = AppendCaseReviewInput.model_json_schema()
    assert schema["properties"]["review_result"]["enum"] == [
        "confirmed",
        "rejected",
        "needs_more_info",
    ]
    assert {item.value for item in SSEEventType} == {
        "intent_identified",
        "data_fetch_started",
        "retrieval_completed",
        "need_user_input",
        "draft_generated",
        "completed",
    }
