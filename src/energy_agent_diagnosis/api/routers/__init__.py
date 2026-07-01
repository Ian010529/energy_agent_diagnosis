"""阶段 1 FastAPI 路由集合。"""

from energy_agent_diagnosis.api.routers.diagnosis import router as diagnosis_router
from energy_agent_diagnosis.api.routers.health import router as health_router
from energy_agent_diagnosis.api.routers.metrics import build_metrics_router
from energy_agent_diagnosis.api.routers.system import router as system_router

__all__ = ["build_metrics_router", "diagnosis_router", "health_router", "system_router"]
