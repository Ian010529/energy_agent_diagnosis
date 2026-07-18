import os

import pytest
import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy import delete

from energy_agent.persistence.models import DiagnosisSessionModel, DiagnosisStepLogModel
from energy_agent.persistence.mysql import create_mysql_engine, create_session_factory

MYSQL_DSN = os.getenv(
    "TEST_MYSQL_DSN",
    "mysql+asyncmy://energy:energy_dev@localhost:3306/energy_agent",
)
REDIS_URL = os.getenv("TEST_REDIS_URL", "redis://127.0.0.1:6379/15")


@pytest_asyncio.fixture
async def mysql_resources():
    engine = create_mysql_engine(MYSQL_DSN)
    factory = create_session_factory(engine)
    async with factory.begin() as session:
        await session.execute(delete(DiagnosisStepLogModel))
        await session.execute(delete(DiagnosisSessionModel))
    yield engine, factory
    await engine.dispose()


@pytest_asyncio.fixture
async def redis_client():
    client = Redis.from_url(REDIS_URL, decode_responses=True)
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


pytestmark = pytest.mark.integration
