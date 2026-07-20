from fastapi.testclient import TestClient

from energy_agent.app import create_app
from energy_agent.core.config import Settings
from energy_agent.core.context import get_context


def test_liveness_contract_and_trace_headers() -> None:
    with TestClient(create_app(Settings(app_env="test"))) as client:
        response = client.get("/health/live", headers={"X-Trace-ID": "invalid"})
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "alive"
    assert body["trace_id"] == response.headers["X-Trace-ID"]
    assert response.headers["X-Request-ID"]
    assert get_context() is None


def test_readiness_contract_when_dependencies_are_down() -> None:
    settings = Settings(
        app_env="test",
        mysql_dsn="mysql+aiomysql://energy:energy_dev@127.0.0.1:1/energy_agent",
        redis_url="redis://127.0.0.1:1/0",
        influxdb_url="http://127.0.0.1:1",
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/health/ready")
    body = response.json()
    assert response.status_code == 503
    assert body["status"] == "not_ready"
    assert body["dependencies"] == {
        "mysql": "down",
        "redis": "down",
        "influxdb": "down",
        "minio": "optional",
        "milvus": "optional",
        "embedding": "optional",
        "reranker": "optional",
        "langfuse": "optional",
    }
