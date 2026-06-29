"""阶段 3 RAG 检索逻辑模块。"""

from energy_agent_diagnosis.core.module import LogicalModule
from energy_agent_diagnosis.retrieval.service import retrieve_evidence


def build_module() -> LogicalModule:
    """创建保留独立部署边界的检索模块。"""
    return LogicalModule(name="retrieval")


__all__ = ["build_module", "retrieve_evidence"]
