"""记忆逻辑模块；阶段 4 使用进程内会话存储，Redis 留给阶段 5。"""

from energy_agent_diagnosis.core.module import LogicalModule
from energy_agent_diagnosis.memory.session_store import (
    DiagnosisSessionRecord,
    InMemoryDiagnosisSessionStore,
)


def build_module() -> LogicalModule:
    """创建保留未来 Redis/案例库拆分边界的记忆模块。"""
    return LogicalModule(name="memory")


__all__ = ["DiagnosisSessionRecord", "InMemoryDiagnosisSessionStore", "build_module"]
