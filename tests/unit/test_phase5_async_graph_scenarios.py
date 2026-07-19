from datetime import UTC, datetime
from typing import cast

import pytest
from pydantic import ValidationError

from energy_agent.agent.state import Evidence
from energy_agent.agent.templates.definitions import TEMPLATES
from energy_agent.agent.templates.registry import (
    TemplateAmbiguousError,
    TemplateRegistry,
)
from energy_agent.agent.templates.rules import evaluate_candidate_rules
from energy_agent.graph.contracts import GraphRelation
from energy_agent.graph.service import GraphService
from energy_agent.indexing.contracts import (
    EntityType,
    IndexJobCreate,
    IndexJobMessage,
    IndexOperation,
    IndexStatus,
    should_dead_letter,
)
from energy_agent.observability.tracing import LocalTracer
from energy_agent.tools.contracts import (
    GraphRelationsInput,
    TimeseriesWindowInput,
    ToolContext,
    ToolStatus,
)
from energy_agent.tools.executor import ToolExecutor
from energy_agent.tools.implementations.graph_tools import register_graph_tool
from energy_agent.tools.registry import ToolRegistry


def _context() -> ToolContext:
    return ToolContext(trace_id="trace", source_system="test")


def test_index_event_schema_status_idempotency_and_retry_decision() -> None:
    event = IndexJobMessage(
        job_id="job",
        entity_type=EntityType.DIAGNOSIS_CASE,
        entity_id="case",
        entity_version="2",
        operation=IndexOperation.UPSERT,
        trace_id="trace",
        correlation_id="session",
        causation_id="review",
        requested_at=datetime.now(UTC),
    )
    assert event.schema_version == 1
    assert IndexStatus.QUEUED == "QUEUED"
    request = IndexJobCreate(
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        entity_version=event.entity_version,
        operation=event.operation,
        trace_id=event.trace_id,
        correlation_id=event.correlation_id,
        causation_id=event.causation_id,
    )
    assert request.idempotency_key == ("diagnosis_case", "case", "2", "upsert")
    assert not should_dead_letter(1, 3, retryable=True)
    assert should_dead_letter(3, 3, retryable=True)
    assert should_dead_letter(1, 3, retryable=False)
    with pytest.raises(ValidationError):
        IndexJobMessage.model_validate({**event.model_dump(), "document_text": "secret"})


def test_five_templates_route_deterministically_and_ambiguity_is_rejected() -> None:
    registry = TemplateRegistry(TEMPLATES)
    cases = {
        ("PCS", "PCS机柜温度持续升高"): "pcs_temperature_abnormal_v1",
        ("PCS", "PCS风扇异常"): "pcs_fan_abnormal_v1",
        ("PCS", "温度传感器异常"): "pcs_temperature_sensor_abnormal_v1",
        ("PV_INVERTER", "光伏逆变器通讯异常"): "pv_inverter_communication_abnormal_v1",
        ("PV_INVERTER", "光伏逆变器功率异常"): "pv_inverter_power_abnormal_v1",
    }
    for (device_type, alarm), expected in cases.items():
        template, basis = registry.route(device_type=device_type, alarm_name=alarm)
        assert template.template_id == expected
        assert "alarm_name" in basis
        assert template.metrics and template.plan_steps and template.candidate_rules
    duplicate = TEMPLATES[0].model_copy(update={"template_id": "duplicate_temperature_v1"})
    with pytest.raises(TemplateAmbiguousError):
        TemplateRegistry([TEMPLATES[0], duplicate]).route(
            device_type="PCS", alarm_name="PCS机柜温度异常"
        )


def test_timeseries_measurements_are_controlled_and_backward_compatible() -> None:
    request = TimeseriesWindowInput(
        context=_context(),
        device_id="PCS-1",
        metrics=["cabinet_temperature"],
        start_time="2026-01-01T00:00:00Z",
        end_time="2026-01-01T00:30:00Z",
    )
    assert request.measurements == ["pcs_metrics"]
    with pytest.raises(ValidationError, match="TIMESERIES_MEASUREMENT_INVALID"):
        TimeseriesWindowInput(
            **request.model_dump(exclude={"measurements"}),
            measurements=['pcs_metrics") |> drop()'],
        )


class _GraphProvider:
    async def query_relations(self, **_: object) -> list[GraphRelation]:
        return [
            GraphRelation(
                alarm_name="风扇异常",
                fault_cause="机械卡滞",
                component="风扇",
                actions=["检查叶轮"],
                support_case_ids=["case-1"],
                support_count=1,
                template_ids=["pcs_fan_abnormal_v1"],
            )
        ]


@pytest.mark.asyncio
async def test_graph_tool_success_and_disabled_degradation() -> None:
    registry = ToolRegistry()
    register_graph_tool(registry, GraphService(cast(object, _GraphProvider())))
    executor = ToolExecutor(registry, LocalTracer())
    payload = GraphRelationsInput(
        context=_context(),
        alarm_name="风扇异常",
        device_type="PCS",
    ).model_dump()
    result = await executor.execute("query_graph_relations", payload, "trace")
    assert result.status == ToolStatus.OK
    assert result.data["relations"][0]["support_count"] == 1

    disabled = ToolRegistry()
    register_graph_tool(disabled, GraphService(None))
    degraded = await ToolExecutor(disabled, LocalTracer()).execute(
        "query_graph_relations", payload, "trace"
    )
    assert degraded.status == ToolStatus.DEGRADED
    assert degraded.error_code == "GRAPH_DISABLED"


def test_graph_only_candidate_remains_manual_confirmation() -> None:
    evidence = Evidence(
        evidence_id="graph:alarm:cause",
        source_type="graph",
        source_id="alarm->cause",
        summary="机柜温度异常可能关联散热风扇失效或转速异常",
        citation="[图谱: 机柜温度异常 -> 散热风扇失效或转速异常]",
        reliability=0.6,
        relevance=0.6,
        need_manual_confirmation=True,
    )
    causes = evaluate_candidate_rules(TEMPLATES[0], [evidence])
    assert causes
    assert all(item.need_manual_confirmation for item in causes)
