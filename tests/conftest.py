"""测试共享配置和 FastAPI 客户端工厂。"""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from energy_agent_diagnosis.app import create_app
from energy_agent_diagnosis.core.config import ApiKeyRecord, AuthSettings, Settings


@pytest.fixture
def test_settings() -> Settings:
    """返回不依赖 Docker、包含一个操作员密钥的隔离配置。"""
    return Settings(
        auth=AuthSettings(
            api_keys=[
                ApiKeyRecord(
                    key="test-api-key",
                    user_id="operator-1",
                    roles=frozenset({"operator"}),
                )
            ]
        )
    )


@pytest_asyncio.fixture
async def client(test_settings: Settings) -> AsyncIterator[AsyncClient]:
    """在完整 lifespan 中运行测试应用。"""
    app = create_app(test_settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as test_client:
            yield test_client
