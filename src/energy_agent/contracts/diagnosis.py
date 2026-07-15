"""Diagnosis acceptance contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from energy_agent.contracts.common import RunStatus, StrictModel, UTCDateTime


class RunAcceptedResponse(StrictModel):
    session_id: str
    run_id: str
    trace_id: str
    acceptance_run_id: str
    status: Literal[RunStatus.ACCEPTED] = RunStatus.ACCEPTED
    accepted_at: UTCDateTime
    revision: int = Field(ge=1)
    events_url: str
    status_url: str
