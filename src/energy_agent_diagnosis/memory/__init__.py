"""记忆逻辑模块；阶段 1 不读写 Redis 或案例库。"""

from energy_agent_diagnosis.core.module import LogicalModule


def build_module() -> LogicalModule:
    """创建不包含会话或案例业务的记忆模块。"""
    return LogicalModule(name="memory")
