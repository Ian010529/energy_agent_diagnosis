"""提供 Provider Registry、Null 骨架和阶段 2 Mock 实现。"""

from energy_agent_diagnosis.ports import ProviderName
from energy_agent_diagnosis.providers.alarm import MockAlarmProvider
from energy_agent_diagnosis.providers.case_review import MockCaseReviewProvider
from energy_agent_diagnosis.providers.device_profile import MockDeviceProfileProvider
from energy_agent_diagnosis.providers.graph_relation import MockGraphRelationProvider
from energy_agent_diagnosis.providers.manual_search import MockManualSearchProvider
from energy_agent_diagnosis.providers.registry import (
    NullProvider,
    ProviderRegistry,
    build_null_registry,
    build_provider_registry,
)
from energy_agent_diagnosis.providers.ticket_search import MockTicketSearchProvider
from energy_agent_diagnosis.providers.ticket_write import MockTicketWriteProvider
from energy_agent_diagnosis.providers.timeseries import MockTimeseriesProvider

__all__ = [
    "MockAlarmProvider",
    "MockCaseReviewProvider",
    "MockDeviceProfileProvider",
    "MockGraphRelationProvider",
    "MockManualSearchProvider",
    "MockTicketSearchProvider",
    "MockTicketWriteProvider",
    "MockTimeseriesProvider",
    "NullProvider",
    "ProviderName",
    "ProviderRegistry",
    "build_null_registry",
    "build_provider_registry",
]
