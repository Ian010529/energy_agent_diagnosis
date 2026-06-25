"""提供进程存活和真实依赖就绪检查。"""

from typing import cast

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from energy_agent_diagnosis.infrastructure.health import HealthService, ProbeStatus

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def live() -> dict[str, str]:
    """只确认应用进程能够处理请求，不访问外部依赖。"""
    return {"status": "alive"}


@router.get("/health/ready")
async def ready(request: Request) -> JSONResponse:
    """探测所有已启用依赖，并用 503 表示必需依赖失败。"""
    health_service = cast(HealthService, request.app.state.health_service)
    report = await health_service.check()
    status_code = 503 if report.status is ProbeStatus.FAILED else 200
    return JSONResponse(status_code=status_code, content=report.model_dump(mode="json"))
