"""手册 chunk 检索 Provider 实现包。"""

from energy_agent_diagnosis.providers.manual_search.mock import MockManualSearchProvider
from energy_agent_diagnosis.providers.manual_search.real import RealManualSearchProvider

__all__ = ["MockManualSearchProvider", "RealManualSearchProvider"]
