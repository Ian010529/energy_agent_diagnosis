"""回归统一错误、Trace、RBAC、指标和日志脱敏的失败路径。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, model_validator

from energy_agent_diagnosis.app import create_app
from energy_agent_diagnosis.core.config import ApiKeyRecord, AuthSettings, Settings
from energy_agent_diagnosis.core.logging import _redact_sensitive_fields


class SensitivePayload(BaseModel):
    """触发包含不可序列化 ctx 的模型级校验错误。"""

    name: str

    @model_validator(mode="after")
    def reject_payload(self) -> "SensitivePayload":
        """使用 ValueError 复现 Pydantic ctx.error。"""
        raise ValueError("payload rejected")


@asynccontextmanager
async def error_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """创建不会把应用异常重新抛给测试进程的客户端。"""
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
        ) as client:
            yield client


@pytest.mark.asyncio
async def test_unexpected_error_keeps_trace_in_body_header_log_and_metrics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    app = create_app(Settings())

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("api_key=must-not-be-logged")

    async with error_client(app) as client:
        response = await client.get("/boom", headers={"X-Trace-ID": "failure-trace"})
        metrics = (await client.get("/metrics")).text

    captured = capsys.readouterr().out
    assert response.status_code == 500
    assert response.json()["trace_id"] == "failure-trace"
    assert response.headers["X-Trace-ID"] == "failure-trace"
    assert "failure-trace" in captured
    assert "must-not-be-logged" not in captured
    assert 'route="/boom",status="500"' in metrics
    assert 'exception_type="RuntimeError",method="GET",route="/boom"' in metrics


@pytest.mark.asyncio
async def test_validation_error_is_safe_and_serializable() -> None:
    app = create_app(Settings())

    @app.post("/validate")
    async def validate(_payload: SensitivePayload) -> None:
        return None

    async with error_client(app) as client:
        response = await client.post("/validate", json={"name": "sensitive-input"})

    assert response.status_code == 422
    assert response.json()["error_code"] == "REQUEST_VALIDATION_FAILED"
    assert "sensitive-input" not in response.text


@pytest.mark.asyncio
async def test_framework_404_and_405_use_standard_error_shape(client: AsyncClient) -> None:
    not_found = await client.get("/missing")
    method_not_allowed = await client.post("/health/live")

    assert not_found.json()["error_code"] == "ROUTE_NOT_FOUND"
    assert method_not_allowed.json()["error_code"] == "METHOD_NOT_ALLOWED"
    assert not_found.json()["trace_id"] == not_found.headers["X-Trace-ID"]


@pytest.mark.asyncio
async def test_authenticated_principal_without_allowed_role_gets_403() -> None:
    settings = Settings(
        auth=AuthSettings(api_keys=[ApiKeyRecord(key="empty-role", user_id="u1", roles=set())])
    )
    app = create_app(settings)

    async with error_client(app) as client:
        response = await client.get(
            "/api/v1/system/ping",
            headers={"X-API-Key": "empty-role"},
        )

    assert response.status_code == 403
    assert response.json()["error_code"] == "PERMISSION_DENIED"


def test_log_redaction_walks_nested_containers() -> None:
    event = {
        "config": {"api_key": "secret-a", "nested": [{"password": "secret-b"}]},
        "safe": "visible",
    }

    redacted = _redact_sensitive_fields(None, "info", event)

    assert redacted["config"] == {"api_key": "***", "nested": [{"password": "***"}]}
    assert redacted["safe"] == "visible"
