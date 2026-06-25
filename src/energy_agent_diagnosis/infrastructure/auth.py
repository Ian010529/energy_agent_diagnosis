"""实现阶段 1 的 API Key 认证 Adapter。"""

import secrets

from energy_agent_diagnosis.contracts import Principal, Role
from energy_agent_diagnosis.core.config import AuthSettings
from energy_agent_diagnosis.core.errors import AppError


class ApiKeyAuthAdapter:
    """把 API Key 安全映射到标准 Principal，后续可替换为企业鉴权。"""

    def __init__(self, settings: AuthSettings) -> None:
        """保存脱敏配置，不建立可被日志直接序列化的明文索引。"""
        self._settings = settings

    async def authenticate(self, credential: str | None) -> Principal:
        """使用常量时间比较验证凭据，降低密钥比较侧信道风险。"""
        if not self._settings.enabled:
            return Principal(user_id="anonymous", roles=frozenset({Role.VIEWER}))
        if not credential:
            raise AppError(
                status_code=401,
                error_code="AUTHENTICATION_REQUIRED",
                message="缺少 API Key",
            )
        for record in self._settings.api_keys:
            if secrets.compare_digest(record.key.get_secret_value(), credential):
                return Principal(user_id=record.user_id, roles=record.roles)
        raise AppError(
            status_code=401,
            error_code="INVALID_API_KEY",
            message="API Key 无效",
        )
