"""检索逻辑模块；阶段 1 不执行召回或重排。"""

from energy_agent_diagnosis.core.module import LogicalModule


def build_module() -> LogicalModule:
    """创建只持有模块边界的检索模块。"""
    return LogicalModule(name="retrieval")
