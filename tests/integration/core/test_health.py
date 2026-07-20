import pytest
from fastapi.testclient import TestClient

from energy_agent.app import create_app
from energy_agent.core.config import Settings

pytestmark = pytest.mark.integration


def test_readiness_with_real_dependencies() -> None:
    settings = Settings(
        app_env="test",
        mysql_dsn="mysql+aiomysql://energy:energy_dev@localhost:3306/energy_agent",
        redis_url="redis://127.0.0.1:6379/15",
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_liveness_does_not_depend_on_dependencies() -> None:
    settings = Settings(
        app_env="test",
        mysql_dsn="mysql+aiomysql://energy:energy_dev@127.0.0.1:1/energy_agent",
        redis_url="redis://127.0.0.1:1/0",
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/health/live")
    assert response.status_code == 200
