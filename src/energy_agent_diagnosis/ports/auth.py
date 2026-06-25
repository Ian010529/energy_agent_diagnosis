"""定义认证调用方与认证实现之间的稳定端口。"""

from typing import Protocol

from energy_agent_diagnosis.contracts import Principal


class AuthPort(Protocol):
    """由 API 调用、由基础设施 Adapter 实现的认证端口。"""

    async def authenticate(self, credential: str | None) -> Principal:
        """校验凭据并返回标准身份；无效凭据应抛出应用错误。"""
        ...
