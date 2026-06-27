"""注册 Provider 实现，并提供未接入能力的 Null 骨架。"""

from enum import StrEnum

from energy_agent_diagnosis.contracts import (
    ProviderType,
    ToolContext,
    ToolMeta,
    ToolResult,
    ToolStatus,
)
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
from energy_agent_diagnosis.providers.alarm import MockAlarmProvider
from energy_agent_diagnosis.providers.device_profile import MockDeviceProfileProvider
from energy_agent_diagnosis.providers.manual_search import MockManualSearchProvider
from energy_agent_diagnosis.providers.ticket_search import MockTicketSearchProvider
from energy_agent_diagnosis.providers.timeseries import MockTimeseriesProvider

ProviderImplementation = (
    DeviceProfileProvider
    | AlarmProvider
    | TimeseriesProvider
    | ManualSearchProvider
    | TicketSearchProvider
    | GraphRelationProvider
    | TicketWriteProvider
    | CaseReviewProvider
)


class ProviderName(StrEnum):
    """八类 Provider 的稳定注册名称。"""

    DEVICE_PROFILE = "device_profile"
    ALARM = "alarm"
    TIMESERIES = "timeseries"
    MANUAL_SEARCH = "manual_search"
    TICKET_SEARCH = "ticket_search"
    GRAPH_RELATION = "graph_relation"
    TICKET_WRITE = "ticket_write"
    CASE_REVIEW = "case_review"


class ProviderRegistry:
    """按稳定名称保存 Provider，避免业务模块依赖具体实现类型。"""

    def __init__(self) -> None:
        """创建空注册表；应用组装层负责注入实现。"""
        self._providers: dict[ProviderName, ProviderImplementation] = {}

    def register(self, name: ProviderName, provider: ProviderImplementation) -> None:
        """注册类型和运行时形状匹配的实现；拒绝错误方法或重复覆盖。"""
        if name in self._providers:
            raise ValueError(f"Provider 已注册: {name}")
        expected_method = {
            ProviderName.DEVICE_PROFILE: "get_device_profile",
            ProviderName.ALARM: "get_alarm_detail",
            ProviderName.TIMESERIES: "query_timeseries_window",
            ProviderName.MANUAL_SEARCH: "search_manual_chunks",
            ProviderName.TICKET_SEARCH: "search_similar_tickets",
            ProviderName.GRAPH_RELATION: "query_graph_relations",
            ProviderName.TICKET_WRITE: "create_or_update_ticket",
            ProviderName.CASE_REVIEW: "append_case_review",
        }[name]
        if not callable(getattr(provider, expected_method, None)):
            raise TypeError(f"Provider {name} 缺少方法: {expected_method}")
        self._providers[name] = provider

    def get(self, name: ProviderName) -> ProviderImplementation:
        """返回实现；缺失时快速失败并指出配置问题。"""
        try:
            return self._providers[name]
        except KeyError as exc:
            raise LookupError(f"Provider 未注册: {name}") from exc

    def names(self) -> frozenset[ProviderName]:
        """返回当前注册名称的不可变快照。"""
        return frozenset(self._providers)


class NullProvider:
    """未配置能力的统一 Provider 骨架，不伪造任何业务数据。"""

    @staticmethod
    def _not_found(context: ToolContext, operation: str) -> ProviderResult:
        """返回可回归的标准空结果，明确当前能力尚未接入。"""
        return ToolResult[Payload](
            success=False,
            status=ToolStatus.NOT_FOUND,
            data={},
            meta=ToolMeta(
                trace_id=context.trace_id,
                source_system="null-provider",
                provider_type="mock",
            ),
            error_code="MOCK_DATA_NOT_CONFIGURED",
            error_message=f"当前阶段未配置该 Provider Mock 数据或能力: {operation}",
        )

    async def get_device_profile(self, context: ToolContext, payload: Payload) -> ProviderResult:
        """返回未配置设备数据。"""
        return self._not_found(context, "get_device_profile")

    async def get_alarm_detail(self, context: ToolContext, payload: Payload) -> ProviderResult:
        """返回未配置告警数据。"""
        return self._not_found(context, "get_alarm_detail")

    async def query_timeseries_window(
        self,
        context: ToolContext,
        payload: Payload,
    ) -> ProviderResult:
        """返回未配置时序数据。"""
        return self._not_found(context, "query_timeseries_window")

    async def search_manual_chunks(self, context: ToolContext, payload: Payload) -> ProviderResult:
        """返回未配置手册数据。"""
        return self._not_found(context, "search_manual_chunks")

    async def search_similar_tickets(
        self,
        context: ToolContext,
        payload: Payload,
    ) -> ProviderResult:
        """返回未配置历史工单。"""
        return self._not_found(context, "search_similar_tickets")

    async def query_graph_relations(
        self,
        context: ToolContext,
        payload: Payload,
    ) -> ProviderResult:
        """返回未配置图谱关系。"""
        return self._not_found(context, "query_graph_relations")

    async def create_or_update_ticket(
        self,
        context: ToolContext,
        payload: Payload,
    ) -> ProviderResult:
        """返回未配置工单写入能力，不执行任何副作用。"""
        return self._not_found(context, "create_or_update_ticket")

    async def append_case_review(self, context: ToolContext, payload: Payload) -> ProviderResult:
        """返回未配置案例审核能力，不执行任何副作用。"""
        return self._not_found(context, "append_case_review")


def build_null_registry() -> ProviderRegistry:
    """为八类工具注册共享的无状态 Null Provider。"""
    registry = ProviderRegistry()
    provider = NullProvider()
    for name in ProviderName:
        registry.register(name, provider)
    return registry


def build_provider_registry(settings: ProviderSettings) -> ProviderRegistry:
    """按配置组装 Provider；未实现 Real 时快速失败，禁止伪装回退。"""
    configured = {
        ProviderName.DEVICE_PROFILE: settings.device_profile,
        ProviderName.ALARM: settings.alarm,
        ProviderName.TIMESERIES: settings.timeseries,
        ProviderName.MANUAL_SEARCH: settings.manual_search,
        ProviderName.TICKET_SEARCH: settings.ticket_search,
        ProviderName.GRAPH_RELATION: settings.graph_relation,
        ProviderName.TICKET_WRITE: settings.ticket_write,
        ProviderName.CASE_REVIEW: settings.case_review,
    }
    unsupported = [
        name.value
        for name, provider_type in configured.items()
        if provider_type is ProviderType.REAL
    ]
    if unsupported:
        raise ValueError(f"尚未实现 Real Provider: {', '.join(unsupported)}")

    registry = ProviderRegistry()
    null_provider = NullProvider()
    # 阶段 2 只启用五个只读 Mock Provider；写入和审核类仍由 NullProvider 明确提示未配置。
    registry.register(ProviderName.DEVICE_PROFILE, MockDeviceProfileProvider())
    registry.register(ProviderName.ALARM, MockAlarmProvider())
    registry.register(ProviderName.TIMESERIES, MockTimeseriesProvider())
    registry.register(ProviderName.MANUAL_SEARCH, MockManualSearchProvider())
    registry.register(ProviderName.TICKET_SEARCH, MockTicketSearchProvider())
    registry.register(ProviderName.GRAPH_RELATION, null_provider)
    registry.register(ProviderName.TICKET_WRITE, null_provider)
    registry.register(ProviderName.CASE_REVIEW, null_provider)
    return registry


# 静态赋值让 Mypy 验证一个 Null 实现同时满足八类端口，而非依赖 object 逃逸类型检查。
_DEVICE_PROFILE_CHECK: DeviceProfileProvider = NullProvider()
_ALARM_CHECK: AlarmProvider = NullProvider()
_TIMESERIES_CHECK: TimeseriesProvider = NullProvider()
_MANUAL_CHECK: ManualSearchProvider = NullProvider()
_TICKET_SEARCH_CHECK: TicketSearchProvider = NullProvider()
_GRAPH_CHECK: GraphRelationProvider = NullProvider()
_TICKET_WRITE_CHECK: TicketWriteProvider = NullProvider()
_CASE_REVIEW_CHECK: CaseReviewProvider = NullProvider()
