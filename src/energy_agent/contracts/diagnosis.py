"""Diagnosis acceptance contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from energy_agent.contracts.common import RunStatus, StrictModel, UTCDateTime, UUIDv7String


class RunAcceptedResponse(StrictModel):
    session_id: UUIDv7String
    run_id: UUIDv7String
    trace_id: UUIDv7String
    acceptance_run_id: UUIDv7String
    status: Literal[RunStatus.ACCEPTED] = RunStatus.ACCEPTED
    accepted_at: UTCDateTime
    revision: int = Field(ge=1)
    events_url: str
    status_url: str
