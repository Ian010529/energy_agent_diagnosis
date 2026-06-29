"""工具逻辑模块；阶段 2 提供统一 Tool/Provider 调用边界。"""

from energy_agent_diagnosis.core.module import LogicalModule
from energy_agent_diagnosis.tools.stage2 import (
    append_case_review,
    create_or_update_ticket,
    get_alarm_detail,
    get_device_profile,
    query_graph_relations,
    query_timeseries_window,
    search_manual_chunks,
    search_similar_tickets,
)


def build_module() -> LogicalModule:
    """创建工具逻辑模块；具体调用通过阶段 2 工具函数执行。"""
    return LogicalModule(name="tools")


__all__ = [
    "append_case_review",
    "build_module",
    "create_or_update_ticket",
    "get_alarm_detail",
    "get_device_profile",
    "query_graph_relations",
    "query_timeseries_window",
    "search_manual_chunks",
    "search_similar_tickets",
]
