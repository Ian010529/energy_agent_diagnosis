"""验证认证 Adapter 的安全比较、角色上下文和禁用模式。"""

import pytest

from energy_agent_diagnosis.contracts import Role
from energy_agent_diagnosis.core.config import ApiKeyRecord, AuthSettings
from energy_agent_diagnosis.core.errors import AppError
from energy_agent_diagnosis.infrastructure.auth import ApiKeyAuthAdapter


@pytest.mark.asyncio
async def test_auth_adapter_accepts_configured_key() -> None:
    adapter = ApiKeyAuthAdapter(
        AuthSettings(api_keys=[ApiKeyRecord(key="secret", user_id="u1", roles={Role.ADMIN})])
    )

    principal = await adapter.authenticate("secret")

    assert principal.user_id == "u1"
    assert principal.roles == {Role.ADMIN}


@pytest.mark.asyncio
async def test_auth_adapter_rejects_invalid_key() -> None:
    adapter = ApiKeyAuthAdapter(AuthSettings())

    with pytest.raises(AppError) as exc_info:
        await adapter.authenticate("wrong")

    assert exc_info.value.error_code == "INVALID_API_KEY"


@pytest.mark.asyncio
async def test_disabled_auth_returns_viewer() -> None:
    principal = await ApiKeyAuthAdapter(AuthSettings(enabled=False)).authenticate(None)

    assert principal.user_id == "anonymous"
    assert principal.roles == {Role.VIEWER}
