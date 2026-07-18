from datetime import UTC, datetime

import pytest

from energy_agent.contracts.common import DiagnosisPhase
from energy_agent.contracts.diagnosis import SessionMemoryPayload
from energy_agent.core.errors import DependencyUnavailableError
from energy_agent.core.ids import new_id
from energy_agent.memory.session_store import RedisSessionStore
from energy_agent.observability.tracing import LocalTracer

pytestmark = pytest.mark.integration


def payload() -> SessionMemoryPayload:
    return SessionMemoryPayload(
        session_id=new_id(),
        phase=DiagnosisPhase.INIT,
        run_id=new_id(),
        trace_id=new_id(),
        updated_at=datetime.now(UTC),
    )


async def test_redis_crud_and_ttl(redis_client) -> None:
    store = RedisSessionStore(redis_client, 60, LocalTracer())
    value = payload()
    assert await store.get(value.session_id, trace_id=value.trace_id) is None
    await store.save(value)
    assert await store.get(value.session_id, trace_id=value.trace_id) == value
    assert 0 < await store.ttl(value.session_id, trace_id=value.trace_id) <= 60
    updated = value.model_copy(update={"phase": DiagnosisPhase.PLAN_READY})
    await store.update(updated)
    assert (await store.get(value.session_id, trace_id=value.trace_id)).phase == (
        DiagnosisPhase.PLAN_READY
    )
    assert await store.delete(value.session_id, trace_id=value.trace_id)
    assert await store.get(value.session_id, trace_id=value.trace_id) is None


async def test_invalid_payload_and_unavailable_redis_are_mapped(redis_client) -> None:
    store = RedisSessionStore(redis_client, 60, LocalTracer())
    value = payload()
    await redis_client.set(store.key(value.session_id), "{invalid")
    with pytest.raises(DependencyUnavailableError, match="payload"):
        await store.get(value.session_id, trace_id=value.trace_id)

    await redis_client.aclose()
    with pytest.raises(DependencyUnavailableError):
        await store.get(value.session_id, trace_id=value.trace_id)
