"""声明 FastAPI 路由使用的认证依赖。"""

from collections.abc import Awaitable, Callable
from typing import Annotated, cast

from fastapi import Depends, Header, Request

from energy_agent_diagnosis.contracts import Principal, Role
from energy_agent_diagnosis.core.errors import AppError
from energy_agent_diagnosis.ports import AuthPort


async def get_current_principal(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> Principal:
    """通过应用组装的 Auth Port 获取标准身份。"""
    auth_port = cast(AuthPort, request.app.state.auth_port)
    return await auth_port.authenticate(x_api_key)


def require_roles(*allowed_roles: Role) -> Callable[..., Awaitable[Principal]]:
    """构造可复用 RBAC 依赖；身份无任一允许角色时返回标准 403。"""
    allowed = frozenset(allowed_roles)

    async def authorize(
        principal: Annotated[Principal, Depends(get_current_principal)],
    ) -> Principal:
        """检查认证身份是否包含路由声明的至少一个角色。"""
        if not principal.roles.intersection(allowed):
            raise AppError(
                status_code=403,
                error_code="PERMISSION_DENIED",
                message="当前角色无权访问该资源",
            )
        return principal

    return authorize
