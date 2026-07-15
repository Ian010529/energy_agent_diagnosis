"""Case lifecycle DTOs."""

from __future__ import annotations

from pydantic import Field

from energy_agent.contracts.common import (
    CaseStatus,
    IndexState,
    StrictModel,
    UTCDateTime,
    UUIDv7String,
)


class CaseRecord(StrictModel):
    case_id: UUIDv7String
    tenant_id: str
    status: CaseStatus
    index_state: IndexState
    version: int = Field(ge=1)
    content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonicalization_version: int = Field(default=2, ge=2, le=2)
    created_at: UTCDateTime
    updated_at: UTCDateTime
