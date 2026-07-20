from datetime import UTC, datetime, timedelta

import pytest
from pydantic import BaseModel, ValidationError

from energy_agent.agent.state import CandidateCause, Evidence, PlanStep
from energy_agent.core.idempotency import request_fingerprint
from energy_agent.observability.tracing import LocalTracer
from energy_agent.providers.influxdb import summarize_points
from energy_agent.retrieval.keyword import rank_rows, relevance_score
from energy_agent.tools.contracts import (
    DeviceProfileInput,
    ToolContext,
    ToolMeta,
    ToolResult,
    ToolStatus,
)
from energy_agent.tools.executor import ToolExecutor
from energy_agent.tools.policies import timeout_seconds_for
from energy_agent.tools.registry import ToolRegistry


def test_phase2_structured_contracts_and_keyword_retrieval() -> None:
    plan = PlanStep(
        step_id="S1",
        goal="查询设备",
        tool="get_device_profile",
        parameters={"device_id": "PCS-1"},
    )
    evidence = Evidence(
        evidence_id="manual:DOC-1",
        source_type="manual",
        source_id="DOC-1",
        summary="检查散热风扇和滤网堵塞",
        citation="[手册: DOC-1 3/page=2]",
        verified=True,
        reliability=1,
        relevance=0.8,
    )
    cause = CandidateCause(
        cause="风扇失效",
        confidence=0.7,
        supporting_evidence=[evidence.evidence_id],
    )
    assert plan.required and cause.supporting_evidence == ["manual:DOC-1"]
    assert relevance_score("PCS 温度 风扇", evidence.summary) > 0
    assert (
        rank_rows(
            "风扇",
            [{"id": "1", "text": "散热风扇异常"}, {"id": "2", "text": "通讯正常"}],
            ("text",),
            1,
        )[0]["id"]
        == "1"
    )


def test_timeseries_summary_and_idempotency_fingerprint() -> None:
    now = datetime.now(UTC)
    summary = summarize_points([(now, 40), (now + timedelta(minutes=1), 45)])
    assert summary == {
        "first": 40,
        "last": 45,
        "min": 40,
        "max": 45,
        "average": 42.5,
        "trend": "rising",
        "point_count": 2,
        "missing": False,
        "quality": "good",
    }
    assert request_fingerprint("x", {"b": 2, "a": 1}) == request_fingerprint("x", {"a": 1, "b": 2})


def test_tool_contract_normalizes_success_and_rejects_invalid_failure() -> None:
    result = ToolResult.model_validate(
        {
            "success": True,
            "status": "SUCCESS",
            "data": {},
            "meta": {
                "trace_id": "trace",
                "source_system": "mysql",
            },
        }
    )
    assert result.status == ToolStatus.OK
    with pytest.raises(ValidationError):
        ToolResult(
            success=False,
            status=ToolStatus.FAILED,
            meta=ToolMeta(trace_id="trace", source_system="mysql"),
        )


@pytest.mark.asyncio
async def test_tool_executor_validates_budget_timeout_and_retry() -> None:
    registry = ToolRegistry()
    attempts = 0

    async def handler(payload: BaseModel) -> ToolResult:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConnectionError
        request = DeviceProfileInput.model_validate(payload)
        return ToolResult(
            success=True,
            status=ToolStatus.OK,
            data={"device_id": request.device_id},
            meta=ToolMeta(trace_id=request.context.trace_id, source_system="mysql"),
        )

    registry.register("get_device_profile", DeviceProfileInput, handler)
    executor = ToolExecutor(registry, LocalTracer())
    arguments = {
        "context": ToolContext(trace_id="trace", source_system="test").model_dump(),
        "device_id": "PCS-1",
    }
    result = await executor.execute("get_device_profile", arguments, "trace")
    assert result.status == ToolStatus.OK
    assert result.meta.attempts == 2
    invalid = await executor.execute("get_device_profile", {}, "trace")
    assert invalid.error_code == "TOOL_ARGUMENT_INVALID"
    for _ in range(7):
        await executor.execute("missing", {}, "trace")
    over_budget = await executor.execute("missing", {}, "trace")
    assert over_budget.error_code == "TOOL_BUDGET_EXCEEDED"


def test_retrieval_tools_have_composite_operation_timeout_budget() -> None:
    assert timeout_seconds_for("get_device_profile") == 5.0
    assert timeout_seconds_for("search_manual_chunks") == 30.0
    assert timeout_seconds_for("search_similar_tickets") == 30.0
