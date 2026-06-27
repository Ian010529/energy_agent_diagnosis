"""提供 Provider Registry、Null 骨架和阶段 2 Mock 实现。"""

from energy_agent_diagnosis.providers.alarm import MockAlarmProvider
from energy_agent_diagnosis.providers.device_profile import MockDeviceProfileProvider
from energy_agent_diagnosis.providers.manual_search import MockManualSearchProvider
from energy_agent_diagnosis.providers.registry import (
    NullProvider,
    ProviderName,
    ProviderRegistry,
    build_null_registry,
    build_provider_registry,
)
from energy_agent_diagnosis.providers.ticket_search import MockTicketSearchProvider
from energy_agent_diagnosis.providers.timeseries import MockTimeseriesProvider

__all__ = [
    "MockAlarmProvider",
    "MockDeviceProfileProvider",
    "MockManualSearchProvider",
    "MockTicketSearchProvider",
    "MockTimeseriesProvider",
    "NullProvider",
    "ProviderName",
    "ProviderRegistry",
    "build_null_registry",
    "build_provider_registry",
]
