"""Agent 编排逻辑模块；阶段 1 仅声明生命周期边界。"""

from energy_agent_diagnosis.core.module import LogicalModule


def build_module() -> LogicalModule:
    """创建不包含 LangGraph 或诊断业务的 Agent 模块。"""
    return LogicalModule(name="agent")
