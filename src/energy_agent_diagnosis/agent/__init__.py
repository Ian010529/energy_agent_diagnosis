"""Agent 编排逻辑模块；阶段 4 提供 LangGraph 主链路。"""

from energy_agent_diagnosis.agent.service import DiagnosisAgentService
from energy_agent_diagnosis.agent.workflow import DiagnosisWorkflow
from energy_agent_diagnosis.core.module import LogicalModule


def build_module() -> LogicalModule:
    """创建 Agent 模块生命周期边界。"""
    return LogicalModule(name="agent")


__all__ = ["DiagnosisAgentService", "DiagnosisWorkflow", "build_module"]
