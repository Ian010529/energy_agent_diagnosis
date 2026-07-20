import pytest

from energy_agent.api.rate_limit import RedisRateLimiter

pytestmark = pytest.mark.integration


class _Redis:
    async def eval(self, script: str, keys: int, key: str, ttl: int, limit: int) -> list[int]:
        assert "actor@example.com" not in key
        return [1, 59]


@pytest.mark.asyncio
async def test_rate_limit_uses_hashed_actor_key() -> None:
    limiter = RedisRateLimiter(_Redis())  # type: ignore[arg-type]
    assert await limiter.allow("actor@example.com", "diagnosis", 10) == (True, 59)
