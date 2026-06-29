"""验证 Null 边界和未实现 Real Adapter 门禁仍然存在。"""

import pytest

from energy_agent_diagnosis.contracts import ToolContext, ToolStatus
from energy_agent_diagnosis.core.config import ProviderSettings
from energy_agent_diagnosis.providers import (
    ProviderName,
    build_null_registry,
    build_provider_registry,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("name", list(ProviderName))
async def test_null_registry_all_operations_return_not_configured(name: ProviderName) -> None:
    """Null Provider 只表达未配置能力，不伪造业务数据。"""
    registry = build_null_registry()
    provider = registry.get(name)
    context = ToolContext(trace_id=f"trace-null-{name}", source_system="test")

    method_name = {
        ProviderName.DEVICE_PROFILE: "get_device_profile",
        ProviderName.ALARM: "get_alarm_detail",
        ProviderName.TIMESERIES: "query_timeseries_window",
        ProviderName.MANUAL_SEARCH: "search_manual_chunks",
        ProviderName.TICKET_SEARCH: "search_similar_tickets",
        ProviderName.GRAPH_RELATION: "query_graph_relations",
        ProviderName.TICKET_WRITE: "create_or_update_ticket",
        ProviderName.CASE_REVIEW: "append_case_review",
    }[name]
    method = getattr(provider, method_name)
    result = await method(context, {})

    assert result.status is ToolStatus.NOT_FOUND
    assert result.error_code == "MOCK_DATA_NOT_CONFIGURED"
    assert result.meta.trace_id == f"trace-null-{name}"


@pytest.mark.parametrize("provider_field", [item.value for item in ProviderName])
def test_real_provider_configuration_fails_fast(provider_field: str) -> None:
    """没有外部接口确认单时，Real 配置不得静默回退到 Mock。"""
    settings = ProviderSettings.model_validate({provider_field: "real"})

    with pytest.raises(ValueError, match="尚未实现 Real Provider"):
        build_provider_registry(settings)
