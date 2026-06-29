"""用矩阵测试验证八类 Mock Provider 的统一契约。"""

from collections.abc import Awaitable, Callable
from typing import cast

import pytest

from energy_agent_diagnosis.contracts import ProviderType, ToolContext, ToolStatus
from energy_agent_diagnosis.core.config import ProviderSettings
from energy_agent_diagnosis.ports.providers import (
    AlarmProvider,
    CaseReviewProvider,
    DeviceProfileProvider,
    GraphRelationProvider,
    ManualSearchProvider,
    Payload,
    ProviderResult,
    TicketSearchProvider,
    TicketWriteProvider,
    TimeseriesProvider,
)
from energy_agent_diagnosis.providers import ProviderName, build_provider_registry

ProviderCall = Callable[[ToolContext, Payload], Awaitable[ProviderResult]]


def get_call(name: ProviderName) -> tuple[ProviderCall, Payload, Payload]:
    """返回 Provider 的成功 payload 和失败 payload。"""
    registry = build_provider_registry(ProviderSettings())
    provider = registry.get(name)
    if name is ProviderName.DEVICE_PROFILE:
        device_provider = cast(DeviceProfileProvider, provider)
        return (
            device_provider.get_device_profile,
            {"device_id": "PCS-10086"},
            {"device_id": "UNKNOWN"},
        )
    if name is ProviderName.ALARM:
        alarm_provider = cast(AlarmProvider, provider)
        return (
            alarm_provider.get_alarm_detail,
            {"alarm_id": "ALARM-20260626-0001"},
            {"alarm_id": "UNKNOWN"},
        )
    if name is ProviderName.TIMESERIES:
        timeseries_provider = cast(TimeseriesProvider, provider)
        return (
            timeseries_provider.query_timeseries_window,
            {"device_id": "PCS-10086", "metrics": ["cabinet_temperature"]},
            {"device_id": "UNKNOWN"},
        )
    if name is ProviderName.MANUAL_SEARCH:
        manual_provider = cast(ManualSearchProvider, provider)
        return (
            manual_provider.search_manual_chunks,
            {"query": "PCS 温度告警 风扇", "filters": {"device_type": "PCS"}},
            {"query": "不存在的检索词"},
        )
    if name is ProviderName.TICKET_SEARCH:
        ticket_provider = cast(TicketSearchProvider, provider)
        return (
            ticket_provider.search_similar_tickets,
            {"query": "SC5000 温度 风扇", "filters": {"device_type": "PCS"}},
            {"query": "不存在的检索词"},
        )
    if name is ProviderName.GRAPH_RELATION:
        graph_provider = cast(GraphRelationProvider, provider)
        return (
            graph_provider.query_graph_relations,
            {"alarm_name": "PCS机柜温度持续升高", "device_type": "PCS"},
            {"alarm_name": "不存在的告警"},
        )
    if name is ProviderName.TICKET_WRITE:
        write_provider = cast(TicketWriteProvider, provider)
        return (
            write_provider.create_or_update_ticket,
            {"action": "create", "device_id": "PCS-10086", "summary": "检查散热风扇"},
            {"action": "delete", "device_id": "PCS-10086", "summary": "非法动作"},
        )
    review_provider = cast(CaseReviewProvider, provider)
    return (
        review_provider.append_case_review,
        {"session_id": "diag_s_001", "review_result": "confirmed", "reviewer": "reviewer-1"},
        {"session_id": "diag_s_001", "review_result": "bad", "reviewer": "reviewer-1"},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("name", list(ProviderName))
async def test_all_mock_providers_return_tool_result_with_trace_and_provider_type(
    name: ProviderName,
) -> None:
    """所有 Mock Provider 成功路径都必须透传 trace 并标记来源类型。"""
    call, success_payload, _ = get_call(name)
    context = ToolContext(trace_id=f"trace-{name}", source_system="test")
    result = await call(context, success_payload)

    assert result.success is True
    assert result.status in {ToolStatus.OK, ToolStatus.PARTIAL_SUCCESS}
    assert result.meta.trace_id == f"trace-{name}"
    assert result.meta.provider_type is ProviderType.MOCK
    assert result.data is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("name", list(ProviderName))
async def test_all_provider_failure_paths_have_error_code_and_stable_data_shape(
    name: ProviderName,
) -> None:
    """所有 Mock Provider 失败路径都必须返回错误码而非未处理异常。"""
    call, _, failure_payload = get_call(name)
    context = ToolContext(trace_id=f"trace-{name}", source_system="test")
    result = await call(context, failure_payload)

    assert result.success is False
    assert result.status in {ToolStatus.NOT_FOUND, ToolStatus.FAILED}
    assert result.error_code
    assert result.meta.trace_id == f"trace-{name}"
    assert result.data is not None
