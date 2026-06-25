"""提供受保护的阶段 1 系统探针。"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from energy_agent_diagnosis.api.dependencies import require_roles
from energy_agent_diagnosis.contracts import Principal, Role
from energy_agent_diagnosis.core.trace import get_trace_id

router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/ping")
async def ping(
    principal: Annotated[
        Principal,
        Depends(require_roles(Role.VIEWER, Role.OPERATOR, Role.REVIEWER, Role.ADMIN)),
    ],
) -> dict[str, Any]:
    """返回当前认证身份和 Trace，用于验证阶段 1 横切能力。"""
    return {
        "status": "ok",
        "user_id": principal.user_id,
        "roles": sorted(principal.roles),
        "trace_id": get_trace_id(),
    }
