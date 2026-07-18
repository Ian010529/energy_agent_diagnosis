from redis.asyncio import Redis


def create_redis_client(url: str) -> Redis:
    return Redis.from_url(url, decode_responses=True)


async def redis_ping(client: Redis) -> None:
    await client.ping()
