"""验证阶段 2 Mock Provider 的契约和可运行性。"""

import json
from pathlib import Path
from typing import cast

import pytest

from energy_agent_diagnosis.contracts import ProviderType, ToolContext, ToolStatus
from energy_agent_diagnosis.core.config import ProviderSettings
from energy_agent_diagnosis.ports import (
    AlarmProvider,
    DeviceProfileProvider,
    GraphRelationProvider,
    ManualSearchProvider,
    TicketSearchProvider,
    TicketWriteProvider,
    TimeseriesProvider,
)
from energy_agent_diagnosis.providers import (
    MockAlarmProvider,
    MockDeviceProfileProvider,
    MockManualSearchProvider,
    MockTicketSearchProvider,
    MockTimeseriesProvider,
    NullProvider,
    ProviderName,
    build_provider_registry,
)

FIXTURE_ROOT = Path(__file__).parents[1] / "src" / "energy_agent_diagnosis" / "fixtures"


def test_stage2_fixtures_are_valid_json_arrays() -> None:
    """运行期 Mock 数据必须是合法 JSON，便于本地回归和联调。"""
    for relative_path in (
        "devices.json",
        "alarms.json",
        "timeseries/summaries.json",
        "manuals/chunks.json",
        "tickets.json",
    ):
        raw: object = json.loads((FIXTURE_ROOT / relative_path).read_text(encoding="utf-8"))
        assert isinstance(raw, list)
        assert raw
        assert all(isinstance(item, dict) for item in raw)


@pytest.mark.asyncio
async def test_device_profile_mock_returns_profile_and_not_found() -> None:
    """设备画像 Mock 成功和失败都必须遵守统一 ToolResult。"""
    provider = MockDeviceProfileProvider()
    context = ToolContext(trace_id="trace-device", source_system="test")

    found = await provider.get_device_profile(context, {"device_id": "PCS-10086"})
    missing = await provider.get_device_profile(context, {"device_id": "UNKNOWN"})

    assert found.status is ToolStatus.OK
    assert found.meta.trace_id == "trace-device"
    assert found.meta.provider_type is ProviderType.MOCK
    assert found.data and found.data["device_model"] == "SC5000"
    assert missing.status is ToolStatus.NOT_FOUND
    assert missing.error_code == "DEVICE_NOT_FOUND"


@pytest.mark.asyncio
async def test_alarm_mock_returns_alarm_and_compatible_time_alias() -> None:
    """告警 Mock 同时暴露 trigger_time 和兼容 alarm_time，贴合文档别名规则。"""
    provider = MockAlarmProvider()
    context = ToolContext(trace_id="trace-alarm", source_system="test")

    result = await provider.get_alarm_detail(
        context,
        {"alarm_id": "ALARM-20260626-0001"},
    )
    missing = await provider.get_alarm_detail(context, {"alarm_id": "UNKNOWN"})

    assert result.status is ToolStatus.OK
    assert result.meta.provider_type is ProviderType.MOCK
    assert result.data and result.data["alarm_time"] == result.data["trigger_time"]
    assert missing.status is ToolStatus.NOT_FOUND
    assert missing.error_code == "ALARM_NOT_FOUND"


@pytest.mark.asyncio
async def test_timeseries_mock_returns_summary_and_partial_result() -> None:
    """时序 Mock 返回摘要；缺部分指标时标记 PARTIAL_SUCCESS 而不是伪装完整。"""
    provider = MockTimeseriesProvider()
    context = ToolContext(trace_id="trace-ts", source_system="test")

    result = await provider.query_timeseries_window(
        context,
        {
            "device_id": "PCS-10086",
            "metrics": ["cabinet_temperature", "not_configured_metric"],
            "start_time": "2026-06-26T09:50:00+08:00",
            "end_time": "2026-06-26T10:20:00+08:00",
        },
    )
    missing = await provider.query_timeseries_window(
        context,
        {"device_id": "UNKNOWN", "metrics": ["cabinet_temperature"]},
    )

    assert result.status is ToolStatus.PARTIAL_SUCCESS
    assert result.meta.partial_result is True
    assert result.data and result.data["missing_metrics"] == ["not_configured_metric"]
    assert missing.status is ToolStatus.NOT_FOUND
    assert missing.error_code == "TIMESERIES_UNAVAILABLE"


@pytest.mark.asyncio
async def test_manual_search_mock_filters_chunks() -> None:
    """手册 Mock 只做阶段 2 基础关键词过滤，不做阶段 3 rerank。"""
    provider = MockManualSearchProvider()
    context = ToolContext(trace_id="trace-manual", source_system="test")

    result = await provider.search_manual_chunks(
        context,
        {
            "query": "PCS 温度告警 风扇",
            "filters": {"device_type": "PCS"},
            "top_k": 2,
            "score_threshold": 0.1,
        },
    )
    missing = await provider.search_manual_chunks(
        context,
        {"query": "不存在的检索词", "filters": {"device_type": "PCS"}},
    )

    assert result.status is ToolStatus.OK
    assert result.data and result.data["count"] >= 1
    assert result.data["chunks"][0]["source_type"] == "manual"
    assert missing.status is ToolStatus.NOT_FOUND
    assert missing.error_code == "RETRIEVAL_FAILED"


@pytest.mark.asyncio
async def test_ticket_search_mock_respects_verified_only() -> None:
    """工单 Mock 默认只返回已审核强证据，关闭 verified_only 后才暴露弱参考。"""
    provider = MockTicketSearchProvider()
    context = ToolContext(trace_id="trace-ticket", source_system="test")

    verified = await provider.search_similar_tickets(
        context,
        {
            "query": "SC5000 温度 风扇",
            "filters": {"device_type": "PCS"},
            "verified_only": True,
            "top_k": 5,
        },
    )
    with_weak = await provider.search_similar_tickets(
        context,
        {
            "query": "SC2500 电流 传感器",
            "filters": {"device_model": "SC2500"},
            "verified_only": False,
            "top_k": 5,
        },
    )
    invalid_verified_flag = await provider.search_similar_tickets(
        context,
        {
            "query": "SC2500 电流 传感器",
            "filters": {"device_model": "SC2500"},
            "verified_only": "false",
            "top_k": 5,
        },
    )
    no_keyword_hit = await provider.search_similar_tickets(
        context,
        {
            "query": "不存在的检索词",
            "filters": {"device_type": "PCS"},
            "verified_only": False,
            "top_k": 5,
        },
    )

    assert verified.status is ToolStatus.OK
    assert verified.data and all(item["is_verified"] is True for item in verified.data["tickets"])
    assert with_weak.status is ToolStatus.OK
    assert with_weak.data and with_weak.data["tickets"][0]["weak_evidence"] is True
    assert invalid_verified_flag.status is ToolStatus.NOT_FOUND
    assert no_keyword_hit.status is ToolStatus.NOT_FOUND


def test_build_provider_registry_uses_stage2_mock_read_providers() -> None:
    """默认 mock 配置应注册阶段 2 只读 Mock，未实现 Real 仍由配置门禁拦住。"""
    registry = build_provider_registry(ProviderSettings())

    assert isinstance(
        cast(DeviceProfileProvider, registry.get(ProviderName.DEVICE_PROFILE)),
        MockDeviceProfileProvider,
    )
    assert isinstance(cast(AlarmProvider, registry.get(ProviderName.ALARM)), MockAlarmProvider)
    assert isinstance(
        cast(TimeseriesProvider, registry.get(ProviderName.TIMESERIES)),
        MockTimeseriesProvider,
    )
    assert isinstance(
        cast(ManualSearchProvider, registry.get(ProviderName.MANUAL_SEARCH)),
        MockManualSearchProvider,
    )
    assert isinstance(
        cast(TicketSearchProvider, registry.get(ProviderName.TICKET_SEARCH)),
        MockTicketSearchProvider,
    )
    assert isinstance(
        cast(GraphRelationProvider, registry.get(ProviderName.GRAPH_RELATION)),
        NullProvider,
    )
    assert isinstance(
        cast(TicketWriteProvider, registry.get(ProviderName.TICKET_WRITE)),
        NullProvider,
    )
    assert isinstance(registry.get(ProviderName.CASE_REVIEW), NullProvider)
