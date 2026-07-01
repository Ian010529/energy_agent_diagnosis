"""图谱关系 Provider 实现包。"""

from energy_agent_diagnosis.providers.graph_relation.mock import MockGraphRelationProvider
from energy_agent_diagnosis.providers.graph_relation.real import RealGraphRelationProvider

__all__ = ["MockGraphRelationProvider", "RealGraphRelationProvider"]
