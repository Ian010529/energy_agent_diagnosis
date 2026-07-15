"""Index-event DTOs."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from energy_agent.contracts.common import StrictModel, UTCDateTime, UUIDv7String


class IndexEvent(StrictModel):
    event_id: UUIDv7String
    event_type: str
    event_version: int = Field(ge=1)
    occurred_at: UTCDateTime
    tenant_id: str
    trace_id: UUIDv7String
    acceptance_run_id: UUIDv7String
    source_type: str
    source_id: str
    source_version: str
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    revision: int = Field(ge=1)
    idempotency_key: str
    payload: dict[str, Any] = Field(default_factory=dict)
