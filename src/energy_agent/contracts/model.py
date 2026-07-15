"""Model-call attempt DTOs; HTTP model invocation belongs to M5."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from energy_agent.contracts.common import StrictModel, UTCDateTime, UUIDv7String


class ModelAttemptStatus(StrEnum):
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ModelAttempt(StrictModel):
    call_id: UUIDv7String
    attempt_no: int = Field(ge=1)
    fencing_token: int = Field(ge=1)
    node_name: str
    prompt_version: str
    prompt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider: str
    model: str
    endpoint_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    trace_id: UUIDv7String
    session_id: UUIDv7String
    run_id: UUIDv7String
    acceptance_run_id: UUIDv7String
    status: ModelAttemptStatus
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonicalization_version: int = Field(default=2, ge=2, le=2)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    estimated_cost: str | None = None
    started_at: UTCDateTime
    finished_at: UTCDateTime | None = None
