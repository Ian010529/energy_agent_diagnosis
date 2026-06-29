"""声明八类工具调用方与 Mock/Real Provider 实现之间的端口。

所有 Mock 与 Real 实现必须接受相同输入、返回同一 ``ToolResult`` 超集，并复用同一套
归一化、错误和契约测试；调用方不得通过实现类型改变处理分支。
"""

from enum import StrEnum
from typing import Any, Protocol

from energy_agent_diagnosis.contracts import ToolContext, ToolResult

Payload = dict[str, Any]
ProviderResult = ToolResult[Payload]


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


class DeviceProfileProvider(Protocol):
    """由工具层调用、由设备台账 Mock 或 Real Adapter 实现。"""

    async def get_device_profile(self, context: ToolContext, payload: Payload) -> ProviderResult:
        """返回标准设备画像结果。"""
        ...


class AlarmProvider(Protocol):
    """由工具层调用、由告警源 Mock 或 Real Adapter 实现。"""

    async def get_alarm_detail(self, context: ToolContext, payload: Payload) -> ProviderResult:
        """返回标准告警详情结果。"""
        ...


class TimeseriesProvider(Protocol):
    """由工具层调用、由时序 Mock 或 Real Adapter 实现。"""

    async def query_timeseries_window(
        self,
        context: ToolContext,
        payload: Payload,
    ) -> ProviderResult:
        """返回标准时序窗口摘要。"""
        ...


class ManualSearchProvider(Protocol):
    """由检索层调用、由手册 Mock 或 Real Adapter 实现。"""

    async def search_manual_chunks(self, context: ToolContext, payload: Payload) -> ProviderResult:
        """返回标准手册片段列表。"""
        ...


class TicketSearchProvider(Protocol):
    """由检索层调用、由工单 Mock 或 Real Adapter 实现。"""

    async def search_similar_tickets(
        self,
        context: ToolContext,
        payload: Payload,
    ) -> ProviderResult:
        """返回标准相似工单列表。"""
        ...


class GraphRelationProvider(Protocol):
    """由检索层调用、由关系 Mock 或 Neo4j Adapter 实现。"""

    async def query_graph_relations(
        self,
        context: ToolContext,
        payload: Payload,
    ) -> ProviderResult:
        """返回标准故障关系结果。"""
        ...


class TicketWriteProvider(Protocol):
    """由受控工具层调用、由工单草稿或真实写入 Adapter 实现。"""

    async def create_or_update_ticket(
        self,
        context: ToolContext,
        payload: Payload,
    ) -> ProviderResult:
        """返回工单草稿或受控写入结果。"""
        ...


class CaseReviewProvider(Protocol):
    """由审核流程调用、由审核记录 Mock 或 Real Adapter 实现。"""

    async def append_case_review(self, context: ToolContext, payload: Payload) -> ProviderResult:
        """返回案例审核记录状态。"""
        ...


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


class ProviderLookup(Protocol):
    """工具层需要的最小 Provider 查找端口。"""

    def get(self, name: ProviderName) -> ProviderImplementation:
        """返回指定 Provider 实现。"""
        ...
