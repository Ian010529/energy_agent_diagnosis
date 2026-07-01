"""历史工单检索 Provider 实现包。"""

from energy_agent_diagnosis.providers.ticket_search.mock import MockTicketSearchProvider
from energy_agent_diagnosis.providers.ticket_search.real import RealTicketSearchProvider

__all__ = ["MockTicketSearchProvider", "RealTicketSearchProvider"]
