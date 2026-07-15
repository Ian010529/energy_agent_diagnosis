"""Frozen HTTP error envelope."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from energy_agent.contracts.common import StrictModel, UUIDv7String


class ErrorDetail(StrictModel):
    code: str
    message: str
    retryable: bool = False
    retry_after_seconds: int | None = Field(default=None, ge=0)
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(StrictModel):
    error: ErrorDetail
    trace_id: UUIDv7String
    acceptance_run_id: UUIDv7String
