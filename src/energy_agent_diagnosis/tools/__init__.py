"""工具逻辑模块；阶段 1 只依赖 Provider Ports。"""

from energy_agent_diagnosis.core.module import LogicalModule


def build_module() -> LogicalModule:
    """创建不包含具体数据访问的工具模块。"""
    return LogicalModule(name="tools")
