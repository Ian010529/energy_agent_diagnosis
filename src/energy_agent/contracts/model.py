"""Model-call attempt DTOs; HTTP model invocation belongs to M5."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from energy_agent.contracts.common import StrictModel, UTCDateTime


class ModelAttemptStatus(StrEnum):
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ModelAttempt(StrictModel):
    call_id: str
    attempt_no: int = Field(ge=1)
    provider: str
    model: str
    status: ModelAttemptStatus
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonicalization_version: int = Field(default=2, ge=2, le=2)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    estimated_cost: str | None = None
    started_at: UTCDateTime
    finished_at: UTCDateTime | None = None
