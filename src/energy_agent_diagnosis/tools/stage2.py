"""阶段 2 工具入口，封装参数校验、Provider 调用和受控写入门禁。"""

from collections.abc import Awaitable, Callable
from typing import cast

from energy_agent_diagnosis.contracts import ToolContext, ToolMeta, ToolResult, ToolStatus
from energy_agent_diagnosis.ports.providers import (
    AlarmProvider,
    CaseReviewProvider,
    DeviceProfileProvider,
    GraphRelationProvider,
    ManualSearchProvider,
    Payload,
    ProviderLookup,
    ProviderName,
    ProviderResult,
    TicketSearchProvider,
    TicketWriteProvider,
    TimeseriesProvider,
)

ToolCall = Callable[[ToolContext, Payload], Awaitable[ProviderResult]]


async def get_device_profile(
    registry: ProviderLookup,
    context: ToolContext,
    payload: Payload,
) -> ProviderResult:
    """查询设备画像，并在进入 Provider 前校验设备 ID。"""
    invalid = _require_string(context, payload, "device_id")
    if invalid:
        return invalid
    provider = cast(DeviceProfileProvider, registry.get(ProviderName.DEVICE_PROFILE))
    return await _call_provider(context, provider.get_device_profile, payload)


async def get_alarm_detail(
    registry: ProviderLookup,
    context: ToolContext,
    payload: Payload,
) -> ProviderResult:
    """查询告警详情，并在进入 Provider 前校验告警 ID。"""
    invalid = _require_string(context, payload, "alarm_id")
    if invalid:
        return invalid
    provider = cast(AlarmProvider, registry.get(ProviderName.ALARM))
    return await _call_provider(context, provider.get_alarm_detail, payload)


async def query_timeseries_window(
    registry: ProviderLookup,
    context: ToolContext,
    payload: Payload,
) -> ProviderResult:
    """查询时序窗口摘要，并保证设备 ID 存在。"""
    invalid = _require_string(context, payload, "device_id")
    if invalid:
        return invalid
    provider = cast(TimeseriesProvider, registry.get(ProviderName.TIMESERIES))
    return await _call_provider(context, provider.query_timeseries_window, payload)


async def search_manual_chunks(
    registry: ProviderLookup,
    context: ToolContext,
    payload: Payload,
) -> ProviderResult:
    """检索手册 chunk，并保证 query 不为空。"""
    invalid = _require_string(context, payload, "query")
    if invalid:
        return invalid
    provider = cast(ManualSearchProvider, registry.get(ProviderName.MANUAL_SEARCH))
    return await _call_provider(context, provider.search_manual_chunks, payload)


async def search_similar_tickets(
    registry: ProviderLookup,
    context: ToolContext,
    payload: Payload,
) -> ProviderResult:
    """检索相似历史工单，并保证 query 不为空。"""
    invalid = _require_string(context, payload, "query")
    if invalid:
        return invalid
    provider = cast(TicketSearchProvider, registry.get(ProviderName.TICKET_SEARCH))
    return await _call_provider(context, provider.search_similar_tickets, payload)


async def query_graph_relations(
    registry: ProviderLookup,
    context: ToolContext,
    payload: Payload,
) -> ProviderResult:
    """查询告警相关图谱关系，并保证告警名存在。"""
    invalid = _require_string(context, payload, "alarm_name")
    if invalid:
        return invalid
    provider = cast(GraphRelationProvider, registry.get(ProviderName.GRAPH_RELATION))
    return await _call_provider(context, provider.query_graph_relations, payload)


async def create_or_update_ticket(
    registry: ProviderLookup,
    context: ToolContext,
    payload: Payload,
) -> ProviderResult:
    """创建或更新工单草稿；没有显式确认时不调用写入 Provider。"""
    invalid = (
        _require_confirmation(context, payload)
        or _require_string(context, payload, "device_id")
        or _require_string(context, payload, "summary")
    )
    if invalid:
        return invalid
    provider = cast(TicketWriteProvider, registry.get(ProviderName.TICKET_WRITE))
    return await _call_provider(context, provider.create_or_update_ticket, payload)


async def append_case_review(
    registry: ProviderLookup,
    context: ToolContext,
    payload: Payload,
) -> ProviderResult:
    """追加人工审核结果；审核人和审核状态必须显式提供。"""
    invalid = (
        _require_string(context, payload, "session_id")
        or _require_string(context, payload, "reviewer")
        or _require_string(context, payload, "review_result")
    )
    if invalid:
        return invalid
    provider = cast(CaseReviewProvider, registry.get(ProviderName.CASE_REVIEW))
    return await _call_provider(context, provider.append_case_review, payload)


async def _call_provider(
    context: ToolContext,
    call: ToolCall,
    payload: Payload,
) -> ProviderResult:
    result = await call(context, payload)
    return ToolResult[Payload].model_validate(result.model_dump())


def _require_string(
    context: ToolContext,
    payload: Payload,
    field_name: str,
) -> ProviderResult | None:
    value = payload.get(field_name)
    if isinstance(value, str) and value.strip():
        return None
    return _failed(context, "INVALID_TOOL_ARGUMENT", f"{field_name} 缺失或非法")


def _require_confirmation(context: ToolContext, payload: Payload) -> ProviderResult | None:
    guard = payload.get("workflow_guard")
    if not isinstance(guard, dict):
        return _failed(context, "NEED_MANUAL_CONFIRMATION", "写入类工具必须提供 workflow_guard")
    token = guard.get("confirmation_token")
    approved = guard.get("approved_by_rule_checker")
    if isinstance(token, str) and token.strip() and approved is True:
        return None
    return _failed(context, "NEED_MANUAL_CONFIRMATION", "写入类工具缺少显式确认")


def _failed(context: ToolContext, error_code: str, message: str) -> ProviderResult:
    return ToolResult[Payload](
        success=False,
        status=ToolStatus.FAILED,
        data={},
        meta=ToolMeta(
            trace_id=context.trace_id,
            source_system="tool-layer",
        ),
        error_code=error_code,
        error_message=message,
    )
