"""验证阶段 2 Tool 层封装 Provider、校验参数和执行确认门禁。"""

import pytest

from energy_agent_diagnosis.contracts import ToolContext, ToolStatus
from energy_agent_diagnosis.core.config import ProviderSettings
from energy_agent_diagnosis.providers import ProviderRegistry, build_provider_registry
from energy_agent_diagnosis.tools import (
    append_case_review,
    create_or_update_ticket,
    get_alarm_detail,
    get_device_profile,
    query_graph_relations,
    query_timeseries_window,
    search_manual_chunks,
    search_similar_tickets,
)


@pytest.fixture
def registry() -> ProviderRegistry:
    """返回默认八类 Mock Provider 注册表。"""
    return build_provider_registry(ProviderSettings())


@pytest.fixture
def context() -> ToolContext:
    """返回可验证 trace 透传的工具上下文。"""
    return ToolContext(trace_id="trace-tool", source_system="test", operator_id="operator-1")


@pytest.mark.asyncio
async def test_tool_layer_passes_trace_context_to_provider(
    registry: ProviderRegistry,
    context: ToolContext,
) -> None:
    """Tool 层调用 Provider 后仍保留统一 ToolResult 元数据。"""
    result = await get_device_profile(registry, context, {"device_id": "PCS-10086"})

    assert result.status is ToolStatus.OK
    assert result.meta.trace_id == "trace-tool"
    assert result.data and result.data["device_id"] == "PCS-10086"


@pytest.mark.asyncio
async def test_tool_layer_validates_required_arguments(
    registry: ProviderRegistry,
    context: ToolContext,
) -> None:
    """Tool 层在参数缺失时直接返回受控错误。"""
    result = await get_alarm_detail(registry, context, {})

    assert result.status is ToolStatus.FAILED
    assert result.error_code == "INVALID_TOOL_ARGUMENT"
    assert result.meta.source_system == "tool-layer"


@pytest.mark.asyncio
async def test_read_only_tools_cover_stage2_data_sources(
    registry: ProviderRegistry,
    context: ToolContext,
) -> None:
    """五类只读数据和图谱关系都能通过 Tool 层访问。"""
    timeseries = await query_timeseries_window(
        registry,
        context,
        {"device_id": "PCS-10086", "metrics": ["cabinet_temperature"]},
    )
    manual = await search_manual_chunks(
        registry,
        context,
        {"query": "PCS 温度告警 风扇", "filters": {"device_type": "PCS"}},
    )
    ticket = await search_similar_tickets(
        registry,
        context,
        {"query": "SC5000 温度 风扇", "filters": {"device_type": "PCS"}},
    )
    graph = await query_graph_relations(
        registry,
        context,
        {"alarm_name": "PCS机柜温度持续升高", "device_type": "PCS"},
    )

    assert timeseries.status is ToolStatus.OK
    assert manual.status is ToolStatus.OK
    assert ticket.status is ToolStatus.OK
    assert graph.status is ToolStatus.OK


@pytest.mark.asyncio
async def test_ticket_write_tool_requires_explicit_confirmation(
    registry: ProviderRegistry,
    context: ToolContext,
) -> None:
    """写入类工具没有显式确认时不调用 Provider。"""
    missing_guard = await create_or_update_ticket(
        registry,
        context,
        {"action": "create", "device_id": "PCS-10086", "summary": "检查散热风扇"},
    )
    confirmed = await create_or_update_ticket(
        registry,
        context,
        {
            "action": "create",
            "device_id": "PCS-10086",
            "summary": "检查散热风扇",
            "workflow_guard": {
                "confirmation_token": "confirm-001",
                "approved_by_rule_checker": True,
            },
        },
    )

    assert missing_guard.status is ToolStatus.FAILED
    assert missing_guard.error_code == "NEED_MANUAL_CONFIRMATION"
    assert confirmed.status is ToolStatus.OK
    assert confirmed.data and confirmed.data["submitted"] is False


@pytest.mark.asyncio
async def test_ticket_write_tool_checks_confirmation_before_payload_shape(
    registry: ProviderRegistry,
    context: ToolContext,
) -> None:
    """写入类工具优先执行确认门禁，避免未确认请求泄露到 Provider。"""
    result = await create_or_update_ticket(registry, context, {})

    assert result.status is ToolStatus.FAILED
    assert result.error_code == "NEED_MANUAL_CONFIRMATION"
    assert result.meta.source_system == "tool-layer"


@pytest.mark.asyncio
async def test_case_review_tool_records_mock_review(
    registry: ProviderRegistry,
    context: ToolContext,
) -> None:
    """案例审核工具通过 Mock Provider 返回审核状态。"""
    result = await append_case_review(
        registry,
        context,
        {
            "session_id": "diag_s_001",
            "review_result": "confirmed",
            "reviewer": "reviewer-1",
        },
    )

    assert result.status is ToolStatus.OK
    assert result.data and result.data["case_status"] == "APPROVED"
