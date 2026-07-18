from fastapi.testclient import TestClient

from energy_agent.app import create_app
from energy_agent.core import lifecycle
from energy_agent.core.config import Settings


class FakeTracer:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def start_trace(self, *args, **kwargs):
        from energy_agent.observability.tracing import LocalSpan

        return LocalSpan("test", "trace", None, "metadata_only")

    start_span = start_trace
    start_generation = start_trace

    async def flush(self) -> None:
        self.events.append("tracer_flush")

    async def shutdown(self) -> None:
        self.events.append("tracer_shutdown")


class FakeEngine:
    async def dispose(self) -> None:
        events.append("mysql")


class FakeRedis:
    async def aclose(self) -> None:
        events.append("redis")


events: list[str] = []


def test_lifespan_closes_resources_in_order(monkeypatch) -> None:
    events.clear()
    monkeypatch.setattr(lifecycle, "create_tracer", lambda settings: FakeTracer(events))
    monkeypatch.setattr(lifecycle, "create_mysql_engine", lambda dsn: FakeEngine())
    monkeypatch.setattr(lifecycle, "create_session_factory", lambda engine: object())
    monkeypatch.setattr(lifecycle, "create_redis_client", lambda url: FakeRedis())
    with TestClient(create_app(Settings(app_env="test"))) as client:
        assert client.get("/health/live").status_code == 200
    assert events == ["tracer_flush", "tracer_shutdown", "redis", "mysql"]
