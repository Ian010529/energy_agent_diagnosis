from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

import energy_agent.contracts as contracts
from energy_agent.contracts import (
    DiagnosisPhase,
    ErrorDetail,
    ErrorEnvelope,
    EventEnvelope,
    ModelAttempt,
    ModelAttemptStatus,
    PublicSSEEvent,
    PublicSSEEventType,
    RunAcceptedResponse,
    RunStatus,
    ToolStatus,
    normalize_legacy_tool_result,
)
from energy_agent.core.config import RuntimeConfig
from energy_agent.core.errors import HTTP_ERROR_POLICIES, error_policy

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 7, 15, tzinfo=UTC)
UUID_1 = "019f64d2-8fd8-70af-8590-c8a509971265"
UUID_2 = "019f64d2-8fd8-70af-8590-c8a509971266"
UUID_3 = "019f64d2-8fd8-70af-8590-c8a509971267"
UUID_4 = "019f64d2-8fd8-70af-8590-c8a509971268"


def enum_values(enum_type: type[StrEnum]) -> set[str]:
    return {member.value for member in enum_type}


def test_frozen_enum_sets_and_unique_names() -> None:
    assert enum_values(contracts.RunStatus) == {
        "ACCEPTED",
        "RUNNING",
        "COMPLETED",
        "NEED_USER_INPUT",
        "FAILED",
    }
    assert enum_values(contracts.DiagnosisPhase) == {
        "INIT",
        "PLAN_READY",
        "DATA_FETCHING",
        "EVIDENCE_READY",
        "NEED_USER_INPUT",
        "DRAFT_READY",
        "REVIEWING",
        "COMPLETED",
        "FAILED",
    }
    assert enum_values(contracts.ToolStatus) == {
        "OK",
        "PARTIAL_SUCCESS",
        "NOT_FOUND",
        "TIMEOUT",
        "DEGRADED",
        "FAILED",
    }
    assert RunStatus.__name__ != DiagnosisPhase.__name__
    assert not hasattr(contracts, "CaseState")
    with pytest.raises(ValueError):
        ToolStatus("SUCCESS")


def test_run_accepted_response_is_strict_and_serializes_utc() -> None:
    response = RunAcceptedResponse.model_validate(
        {
            "session_id": UUID_1,
            "run_id": UUID_2,
            "trace_id": UUID_3,
            "acceptance_run_id": UUID_4,
            "accepted_at": "2026-07-15T08:00:00+08:00",
            "revision": 2,
            "events_url": "/events",
            "status_url": "/status",
        }
    )
    assert response.model_dump(mode="json")["accepted_at"] == "2026-07-15T00:00:00.000000Z"
    with pytest.raises(ValidationError):
        RunAcceptedResponse.model_validate({**response.model_dump(), "unknown": True})
    with pytest.raises(ValidationError, match="UUIDv7"):
        RunAcceptedResponse.model_validate({**response.model_dump(), "session_id": "session"})


def test_http_error_shape_and_mapping() -> None:
    envelope = ErrorEnvelope(
        error=ErrorDetail(code="NOT_FOUND", message="missing"),
        trace_id=UUID_1,
        acceptance_run_id=UUID_2,
    )
    assert envelope.model_dump() == {
        "error": {
            "code": "NOT_FOUND",
            "message": "missing",
            "retryable": False,
            "retry_after_seconds": None,
            "details": {},
        },
        "trace_id": UUID_1,
        "acceptance_run_id": UUID_2,
    }
    assert set(HTTP_ERROR_POLICIES) == {401, 403, 404, 409, 422, 429, 500, 503, 504}
    assert error_policy(429).retryable
    assert not error_policy(409).retryable


def test_public_sse_is_six_events_and_phase_bound() -> None:
    assert enum_values(PublicSSEEventType) == {
        "intent_identified",
        "data_fetch_started",
        "retrieval_completed",
        "need_user_input",
        "draft_generated",
        "completed",
    }
    event = PublicSSEEvent(
        event_id=UUID_1,
        sequence=1,
        event_type=PublicSSEEventType.RETRIEVAL_COMPLETED,
        event_version=1,
        session_id=UUID_2,
        run_id=UUID_3,
        trace_id=UUID_4,
        acceptance_run_id=UUID_1,
        phase=DiagnosisPhase.EVIDENCE_READY,
        occurred_at=NOW,
        message="done",
        payload={"nullable": None},
    )
    assert event.payload == {"nullable": None}
    with pytest.raises(ValidationError, match="does not match"):
        PublicSSEEvent.model_validate(
            {**event.model_dump(), "event_type": PublicSSEEventType.COMPLETED}
        )


def test_event_envelope_uses_exact_idempotency_key_field() -> None:
    value = {
        "event_id": UUID_1,
        "event_type": "manual.index.requested",
        "event_version": 1,
        "occurred_at": NOW,
        "tenant_id": "pilot",
        "trace_id": UUID_2,
        "acceptance_run_id": UUID_3,
        "aggregate_type": "manual_document",
        "aggregate_id": UUID_4,
        "revision": 1,
        "idempotency_key": "stable-key",
        "payload": {},
    }
    assert EventEnvelope.model_validate(value).idempotency_key == "stable-key"
    value["idempotency_key_hash"] = value.pop("idempotency_key")
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(value)


def test_legacy_success_is_only_read_boundary_mapping() -> None:
    result = normalize_legacy_tool_result(
        {
            "status": "SUCCESS",
            "success": True,
            "data": {"value": 1},
            "meta": {
                "trace_id": UUID_1,
                "source_system": "ems",
                "provider_type": "real",
                "partial_result": False,
                "latency_ms": 12,
            },
            "error_code": "",
            "error_message": "",
            "warnings": [],
        }
    )
    assert result.status is ToolStatus.OK
    assert "SUCCESS" not in json.dumps(result.model_dump(mode="json"))


def valid_config() -> dict[str, Any]:
    def secret(name: str) -> dict[str, str]:
        return {"env_name": name, "secret_ref": f"vault://m1/{name.lower()}"}

    return {
        "deployment_profile": "full",
        "app": {"endpoint": "https://agent.example.com", "runtime_source": "service"},
        "auth": {
            "issuer": "https://identity.example.com",
            "audience": "energy-agent",
            "client_secret": secret("AUTH_CLIENT_SECRET"),
        },
        "control_mysql": {
            "endpoint": "mysql://control:3306",
            "database": "control",
            "username": "agent",
            "password": secret("CONTROL_MYSQL_PASSWORD"),
        },
        "ops_mysql": {
            "endpoint": "mysql://ops:3306",
            "database": "ops",
            "username": "agent",
            "password": secret("OPS_MYSQL_PASSWORD"),
        },
        "redis": {
            "endpoint": "redis://redis:6379",
            "password": secret("REDIS_PASSWORD"),
        },
        "storage": {
            "endpoint": "https://storage.example.com",
            "bucket": "manuals",
            "access_key": secret("STORAGE_ACCESS_KEY"),
            "secret_key": secret("STORAGE_SECRET_KEY"),
        },
        "model_gateway": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "endpoint": "https://api.openai.com/v1/chat/completions",
            "api_key": secret("OPENAI_API_KEY"),
        },
        "retrieval": {
            "endpoint": "https://retrieval.example.com",
            "provider": "retrieval-api",
        },
        "observability": {
            "endpoint": "https://cloud.langfuse.com",
            "public_key": secret("LANGFUSE_PUBLIC_KEY"),
            "secret_key": secret("LANGFUSE_SECRET_KEY"),
        },
    }


@pytest.mark.parametrize("marker", ["mock", "fixture", "sandbox", "gold", "d3_dev", ".json"])
def test_protected_config_rejects_forbidden_runtime_sources(marker: str) -> None:
    value = valid_config()
    value["app"] = {"endpoint": "https://agent.example.com", "runtime_source": marker}
    with pytest.raises(ValidationError, match="forbidden runtime"):
        RuntimeConfig.model_validate(value)


def test_config_rejects_unapproved_model_and_placeholder_secret() -> None:
    value = valid_config()
    model = dict(value["model_gateway"])
    model["model"] = "unapproved"
    value["model_gateway"] = model
    with pytest.raises(ValidationError, match="not approved"):
        RuntimeConfig.model_validate(value)

    value = valid_config()
    auth = dict(value["auth"])
    auth["client_secret"] = {"env_name": "AUTH_CLIENT_SECRET", "secret_ref": "placeholder"}
    value["auth"] = auth
    with pytest.raises(ValidationError, match="placeholder"):
        RuntimeConfig.model_validate(value)


@pytest.mark.parametrize(
    ("section", "field"),
    (
        ("auth", "issuer"),
        ("redis", "endpoint"),
        ("storage", "endpoint"),
        ("retrieval", "endpoint"),
        ("observability", "endpoint"),
    ),
)
def test_protected_config_checks_every_dependency_endpoint(section: str, field: str) -> None:
    value = valid_config()
    config_section = dict(value[section])
    config_section[field] = "https://fixture.example.com"
    value[section] = config_section
    with pytest.raises(ValidationError, match="forbidden runtime"):
        RuntimeConfig.model_validate(value)


def test_secret_reference_rejects_and_redacts_literal_secret_values() -> None:
    literal = "sk-sensitive-literal-value"
    value = valid_config()
    auth = dict(value["auth"])
    auth["client_secret"] = {"env_name": "AUTH_CLIENT_SECRET", "secret_ref": literal}
    value["auth"] = auth
    with pytest.raises(ValidationError) as captured:
        RuntimeConfig.model_validate(value)
    assert literal not in str(captured.value)

    config = RuntimeConfig.model_validate(valid_config())
    serialized = config.model_dump_json()
    assert "vault://" not in serialized
    assert "**********" in serialized


def test_model_attempt_freezes_governance_and_fencing_identity() -> None:
    attempt = ModelAttempt(
        call_id=UUID_1,
        attempt_no=1,
        fencing_token=2,
        node_name="reason_generator",
        prompt_version="diag.reason_generator.1.0",
        prompt_digest="a" * 64,
        provider="openai",
        model="gpt-4o-mini",
        endpoint_digest="b" * 64,
        trace_id=UUID_2,
        session_id=UUID_3,
        run_id=UUID_4,
        acceptance_run_id=UUID_1,
        status=ModelAttemptStatus.STARTED,
        request_digest="c" * 64,
        started_at=NOW,
    )
    assert attempt.fencing_token == 2


def test_business_source_only_reads_environment_in_config_boundary() -> None:
    offenders: list[str] = []
    for path in (ROOT / "src/energy_agent").rglob("*.py"):
        if path.name == "config.py":
            continue
        source = path.read_text(encoding="utf-8")
        if "os.environ" in source or "os.getenv" in source:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
