"""验证逻辑模块生命周期和 Null Provider 注册契约。"""

from typing import cast

import pytest

from energy_agent_diagnosis.app import create_app
from energy_agent_diagnosis.contracts import ToolContext, ToolStatus
from energy_agent_diagnosis.core.config import ProviderSettings, Settings
from energy_agent_diagnosis.ports import AlarmProvider
from energy_agent_diagnosis.providers import (
    NullProvider,
    ProviderName,
    ProviderRegistry,
    build_null_registry,
    build_provider_registry,
)


@pytest.mark.asyncio
async def test_all_logical_modules_initialize_and_shutdown() -> None:
    app = create_app(Settings())
    async with app.router.lifespan_context(app):
        assert {module.name for module in app.state.modules} == {
            "agent",
            "retrieval",
            "tools",
            "memory",
        }
        assert all(module.initialized for module in app.state.modules)
    assert all(not module.initialized for module in app.state.modules)


def test_null_registry_contains_all_provider_names() -> None:
    registry = build_null_registry()

    assert registry.names() == frozenset(ProviderName)


def test_registry_rejects_duplicates_and_missing_provider() -> None:
    registry = ProviderRegistry()
    registry.register(ProviderName.ALARM, NullProvider())

    with pytest.raises(ValueError):
        registry.register(ProviderName.ALARM, NullProvider())
    with pytest.raises(LookupError):
        registry.get(ProviderName.TIMESERIES)


@pytest.mark.asyncio
async def test_null_provider_returns_standard_not_found() -> None:
    result = await NullProvider().get_device_profile(
        ToolContext(trace_id="trace-1", source_system="test"),
        {"device_id": "device-1"},
    )

    assert result.status is ToolStatus.NOT_FOUND
    assert result.error_code == "MOCK_DATA_NOT_CONFIGURED"
    assert result.meta.provider_type == "mock"


@pytest.mark.parametrize(
    "provider_field",
    [
        "device_profile",
        "alarm",
        "timeseries",
        "manual_search",
        "ticket_search",
        "graph_relation",
        "ticket_write",
        "case_review",
    ],
)
def test_real_provider_configuration_fails_instead_of_mock_fallback(
    provider_field: str,
) -> None:
    settings = ProviderSettings.model_validate({provider_field: "real"})

    with pytest.raises(ValueError, match="尚未实现 Real Provider"):
        build_provider_registry(settings)


def test_registry_rejects_provider_with_wrong_runtime_shape() -> None:
    registry = ProviderRegistry()

    with pytest.raises(TypeError, match="缺少方法"):
        registry.register(ProviderName.ALARM, cast(AlarmProvider, object()))
