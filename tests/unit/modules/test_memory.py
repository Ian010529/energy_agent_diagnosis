import pytest

from energy_agent.contracts.common import DiagnosisPhase
from energy_agent.contracts.diagnosis import SessionMemoryPayload
from energy_agent.core.time import utc_now
from energy_agent.memory.session_store import RedisSessionStore
from energy_agent.observability.tracing import LocalTracer


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}

    async def set(self, key: str, value: str, *, ex: int) -> None:
        self.values[key] = value
        self.expirations[key] = ex

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def delete(self, key: str) -> int:
        existed = key in self.values
        self.values.pop(key, None)
        return int(existed)

    async def ttl(self, key: str) -> int:
        return self.expirations.get(key, -2)


@pytest.mark.asyncio
async def test_session_memory_round_trip_ttl_and_delete() -> None:
    redis = FakeRedis()
    store = RedisSessionStore(redis, ttl_seconds=600, tracer=LocalTracer())  # type: ignore[arg-type]
    payload = SessionMemoryPayload(
        session_id="session-1",
        run_id="run-1",
        trace_id="trace-1",
        phase=DiagnosisPhase.PLAN_READY,
        updated_at=utc_now(),
    )

    await store.save(payload)

    restored = await store.get("session-1", trace_id="trace-1")
    assert restored == payload
    assert await store.ttl("session-1", trace_id="trace-1") == 600
    assert await store.delete("session-1", trace_id="trace-1") is True
    assert await store.get("session-1", trace_id="trace-1") is None
