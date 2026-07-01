"""验证阶段 1 API、认证、Trace、错误和指标行为。"""

import pytest
from httpx import ASGITransport, AsyncClient

from energy_agent_diagnosis.app import create_app
from energy_agent_diagnosis.core.config import MetricsSettings, Settings


@pytest.mark.asyncio
async def test_live_and_ready_without_enabled_dependencies(client: AsyncClient) -> None:
    live = await client.get("/health/live")
    ready = await client.get("/health/ready")

    assert live.status_code == 200
    assert live.json() == {"status": "alive"}
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready", "dependencies": []}


@pytest.mark.asyncio
async def test_ping_requires_api_key_and_returns_principal(client: AsyncClient) -> None:
    missing = await client.get("/api/v1/system/ping")
    accepted = await client.get(
        "/api/v1/system/ping",
        headers={"X-API-Key": "test-api-key", "X-Trace-ID": "caller-trace-1"},
    )

    assert missing.status_code == 401
    assert missing.json()["error_code"] == "AUTHENTICATION_REQUIRED"
    assert missing.headers["X-Trace-ID"]
    assert accepted.status_code == 200
    assert accepted.headers["X-Trace-ID"] == "caller-trace-1"
    assert accepted.json() == {
        "status": "ok",
        "user_id": "operator-1",
        "roles": ["operator"],
        "trace_id": "caller-trace-1",
    }


@pytest.mark.asyncio
async def test_invalid_trace_is_replaced(client: AsyncClient) -> None:
    response = await client.get(
        "/health/live",
        headers={"X-Trace-ID": "unsafe trace\nvalue"},
    )

    assert response.status_code == 200
    assert response.headers["X-Trace-ID"] != "unsafe trace\nvalue"
    assert len(response.headers["X-Trace-ID"]) == 32


@pytest.mark.asyncio
async def test_metrics_are_exposed_without_high_cardinality_labels(client: AsyncClient) -> None:
    await client.get("/health/live")
    response = await client.get("/metrics")
    body = response.text

    assert response.status_code == 200
    assert "energy_diagnosis_http_requests_total" in body
    assert 'route="/health/live"' in body
    assert "trace_id=" not in body


@pytest.mark.asyncio
async def test_openapi_contains_stage4_diagnosis_routes(client: AsyncClient) -> None:
    schema = (await client.get("/openapi.json")).json()

    assert "/health/live" in schema["paths"]
    assert "/health/ready" in schema["paths"]
    assert "/api/v1/system/ping" in schema["paths"]
    assert "/api/v1/diagnosis/chat" in schema["paths"]
    assert "/api/v1/diagnosis/sessions/{session_id}/events" in schema["paths"]
    assert "/metrics" not in schema["paths"]


@pytest.mark.asyncio
async def test_metrics_path_uses_configuration() -> None:
    app = create_app(Settings(metrics=MetricsSettings(path="/internal/metrics")))
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as custom_client:
            configured = await custom_client.get("/internal/metrics")
            old_path = await custom_client.get("/metrics")

    assert configured.status_code == 200
    assert old_path.status_code == 404
