"""Schema manifest and migration result DTOs."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field

from energy_agent.contracts.common import StrictModel, UTCDateTime


class MigrationStatus(StrEnum):
    APPLIED = "APPLIED"
    ALREADY_APPLIED = "ALREADY_APPLIED"
    FAILED = "FAILED"


class SchemaManifest(StrictModel):
    schema_name: str
    manifest_version: int = Field(ge=1)
    canonicalization_version: int = Field(default=2, ge=2, le=2)
    migration_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    descriptor: dict[str, Any]
    created_at: UTCDateTime


class MigrationResult(StrictModel):
    schema_name: str
    version: str
    status: MigrationStatus
    migration_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    applied_steps: int = Field(ge=0)
    finished_at: UTCDateTime
