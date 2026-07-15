"""Index-event DTOs."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from energy_agent.contracts.common import StrictModel, UTCDateTime


class IndexEvent(StrictModel):
    event_id: str
    event_type: str
    event_version: int = Field(ge=1)
    occurred_at: UTCDateTime
    tenant_id: str
    trace_id: str
    acceptance_run_id: str
    source_type: str
    source_id: str
    source_version: str
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    revision: int = Field(ge=1)
    idempotency_key: str
    payload: dict[str, Any] = Field(default_factory=dict)
