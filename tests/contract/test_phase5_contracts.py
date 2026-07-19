from datetime import UTC, datetime

from energy_agent.agent.templates.contracts import DiagnosisTemplate
from energy_agent.agent.templates.definitions import TEMPLATES
from energy_agent.app import create_app
from energy_agent.contracts.cases import CaseIndexStatus, DiagnosisCase
from energy_agent.contracts.events import SSEEventType
from energy_agent.indexing.contracts import IndexJobMessage
from energy_agent.retrieval.contracts import EvidencePackage, SourceType
from energy_agent.tools.contracts import GraphRelationsInput, TimeseriesWindowInput


def test_phase5_strict_index_graph_and_template_contracts() -> None:
    schema = IndexJobMessage.model_json_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) >= {
        "job_id",
        "entity_type",
        "entity_id",
        "entity_version",
        "operation",
        "trace_id",
    }
    assert GraphRelationsInput.model_json_schema()["additionalProperties"] is False
    assert len(TEMPLATES) == 5
    assert all(isinstance(item, DiagnosisTemplate) for item in TEMPLATES)
    assert len({item.device_type for item in TEMPLATES}) == 2


def test_phase5_evidence_timeseries_case_and_sse_compatibility() -> None:
    assert SourceType.GRAPH == "graph"
    assert "graph_relations" in EvidencePackage.model_fields
    assert TimeseriesWindowInput.model_fields["measurements"].is_required() is False
    assert {"QUEUED", "RUNNING", "DEGRADED"} <= {item.value for item in CaseIndexStatus}
    assert {
        "index_job_id",
        "graph_projection_status",
    } <= DiagnosisCase.model_fields.keys()
    assert {item.value for item in SSEEventType} == {
        "intent_identified",
        "data_fetch_started",
        "retrieval_completed",
        "need_user_input",
        "draft_generated",
        "completed",
    }


def test_phase5_public_api_paths_remain_compatible() -> None:
    paths = create_app().openapi()["paths"]
    assert "/api/v1/diagnosis/chat" in paths
    assert "/api/v1/cases/{case_id}/reindex" in paths
    message = IndexJobMessage(
        job_id="job",
        entity_type="template_graph",
        entity_id="pcs_temperature_abnormal_v1",
        entity_version="1.0.0",
        operation="graph_project",
        trace_id="trace",
        correlation_id="bootstrap",
        causation_id="bootstrap",
        requested_at=datetime.now(UTC),
    )
    assert "embedding" not in message.model_dump()
