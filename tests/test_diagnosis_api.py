"""验证阶段 4 诊断 API、幂等和 SSE 事件。"""

import json

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_diagnosis_chat_requires_auth_and_preserves_trace(client: AsyncClient) -> None:
    missing = await client.post(
        "/api/v1/diagnosis/chat",
        json={"alarm_id": "ALARM-20260626-0001", "message": "PCS机柜温度持续升高"},
    )
    accepted = await client.post(
        "/api/v1/diagnosis/chat",
        headers={"X-API-Key": "test-api-key", "X-Trace-ID": "trace-diag-api"},
        json={"alarm_id": "ALARM-20260626-0001", "message": "PCS机柜温度持续升高"},
    )

    assert missing.status_code == 401
    assert accepted.status_code == 200
    assert accepted.headers["X-Trace-ID"] == "trace-diag-api"
    body = accepted.json()
    assert body["status"] == "COMPLETED"
    assert body["trace_id"] == "trace-diag-api"
    assert body["result"]["candidate_causes"]


@pytest.mark.asyncio
async def test_create_session_idempotency_returns_same_session(client: AsyncClient) -> None:
    headers = {
        "X-API-Key": "test-api-key",
        "X-Trace-ID": "trace-idem",
        "X-Idempotency-Key": "idem-create-1",
    }

    first = await client.post(
        "/api/v1/diagnosis/sessions",
        headers=headers,
        json={"alarm_id": "ALARM-20260626-0001", "message": "PCS机柜温度持续升高"},
    )
    second = await client.post(
        "/api/v1/diagnosis/sessions",
        headers=headers,
        json={"alarm_id": "ALARM-20260626-0002", "message": "另一个请求"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["session_id"] == second.json()["session_id"]


@pytest.mark.asyncio
async def test_duplicate_explicit_session_id_returns_standard_conflict(
    client: AsyncClient,
) -> None:
    headers = {"X-API-Key": "test-api-key", "X-Trace-ID": "trace-conflict"}
    payload = {
        "session_id": "diag-explicit-conflict",
        "alarm_id": "ALARM-20260626-0001",
        "message": "PCS机柜温度持续升高",
    }

    first = await client.post("/api/v1/diagnosis/sessions", headers=headers, json=payload)
    second = await client.post("/api/v1/diagnosis/sessions", headers=headers, json=payload)

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error_code"] == "SESSION_ALREADY_EXISTS"


@pytest.mark.asyncio
async def test_missing_diagnosis_session_returns_standard_not_found(
    client: AsyncClient,
) -> None:
    response = await client.get(
        "/api/v1/diagnosis/sessions/not-found",
        headers={"X-API-Key": "test-api-key"},
    )
    events = await client.get(
        "/api/v1/diagnosis/sessions/not-found/events",
        headers={"X-API-Key": "test-api-key"},
    )

    assert response.status_code == 404
    assert response.json()["error_code"] == "SESSION_NOT_FOUND"
    assert events.status_code == 404
    assert events.json()["error_code"] == "SESSION_NOT_FOUND"


@pytest.mark.asyncio
async def test_message_idempotency_returns_existing_snapshot(client: AsyncClient) -> None:
    create = await client.post(
        "/api/v1/diagnosis/sessions",
        headers={"X-API-Key": "test-api-key", "X-Trace-ID": "trace-msg-idem"},
        json={"alarm_id": "ALARM-20260626-0001", "message": "PCS机柜温度持续升高"},
    )
    session_id = create.json()["session_id"]
    headers = {
        "X-API-Key": "test-api-key",
        "X-Trace-ID": "trace-msg-idem",
        "X-Idempotency-Key": "idem-message-1",
    }

    first = await client.post(
        f"/api/v1/diagnosis/sessions/{session_id}/messages",
        headers=headers,
        json={"message": "PCS机柜温度持续升高"},
    )
    second = await client.post(
        f"/api/v1/diagnosis/sessions/{session_id}/messages",
        headers=headers,
        json={"message": "重复提交但不应重复执行"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["events"] == second.json()["events"]


@pytest.mark.asyncio
async def test_diagnosis_sse_events_use_document_payload_shape(client: AsyncClient) -> None:
    chat = await client.post(
        "/api/v1/diagnosis/chat",
        headers={"X-API-Key": "test-api-key", "X-Trace-ID": "trace-sse"},
        json={"alarm_id": "ALARM-20260626-0003", "message": "逆变器通讯中断"},
    )
    session_id = chat.json()["session_id"]

    response = await client.get(
        f"/api/v1/diagnosis/sessions/{session_id}/events",
        headers={"X-API-Key": "test-api-key"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: retrieval_completed" in response.text
    assert "event: diagnosis_completed" in response.text
    data_line = next(line for line in response.text.splitlines() if line.startswith("data: "))
    event_payload = json.loads(data_line.removeprefix("data: "))
    assert {"event", "session_id", "trace_id", "timestamp", "payload"}.issubset(event_payload)
    assert {"message", "progress", "data"}.issubset(event_payload["payload"])
