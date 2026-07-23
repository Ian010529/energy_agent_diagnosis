import hashlib
from typing import Protocol

from redis.asyncio import Redis

_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
local ttl = redis.call('TTL', KEYS[1])
if current > tonumber(ARGV[2]) then return {0, ttl} end
return {1, ttl}
"""
_ACQUIRE_CONCURRENT_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
redis.call('EXPIRE', KEYS[1], ARGV[2])
if current > tonumber(ARGV[1]) then
  redis.call('DECR', KEYS[1])
  return 0
end
return 1
"""
_RELEASE_CONCURRENT_SCRIPT = """
local current = redis.call('DECR', KEYS[1])
if current <= 0 then redis.call('DEL', KEYS[1]) end
return current
"""


class RateLimiter(Protocol):
    async def allow(self, actor_id: str, group: str, limit: int) -> tuple[bool, int]: ...

    async def acquire_stream(self, actor_id: str, limit: int) -> bool: ...

    async def release_stream(self, actor_id: str) -> None: ...


class RedisRateLimiter:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    @staticmethod
    def actor_hash(actor_id: str) -> str:
        return hashlib.sha256(actor_id.encode()).hexdigest()[:24]

    async def allow(self, actor_id: str, group: str, limit: int) -> tuple[bool, int]:
        key = f"rate:v1:{group}:{self.actor_hash(actor_id)}"
        allowed, ttl = await self.redis.eval(_SCRIPT, 1, key, 60, limit)
        return bool(allowed), max(1, int(ttl))

    async def acquire_stream(self, actor_id: str, limit: int) -> bool:
        key = f"rate:v1:stream:{self.actor_hash(actor_id)}"
        allowed = await self.redis.eval(_ACQUIRE_CONCURRENT_SCRIPT, 1, key, limit, 300)
        return bool(allowed)

    async def release_stream(self, actor_id: str) -> None:
        key = f"rate:v1:stream:{self.actor_hash(actor_id)}"
        await self.redis.eval(_RELEASE_CONCURRENT_SCRIPT, 1, key)
