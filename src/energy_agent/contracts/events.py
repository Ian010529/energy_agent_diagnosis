"""Internal event and public SSE schemas."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field, model_validator

from energy_agent.contracts.common import DiagnosisPhase, StrictModel, UTCDateTime


class PublicSSEEventType(StrEnum):
    INTENT_IDENTIFIED = "intent_identified"
    DATA_FETCH_STARTED = "data_fetch_started"
    RETRIEVAL_COMPLETED = "retrieval_completed"
    NEED_USER_INPUT = "need_user_input"
    DRAFT_GENERATED = "draft_generated"
    COMPLETED = "completed"


PHASE_EVENT_TYPES: dict[DiagnosisPhase, PublicSSEEventType] = {
    DiagnosisPhase.INIT: PublicSSEEventType.INTENT_IDENTIFIED,
    DiagnosisPhase.PLAN_READY: PublicSSEEventType.INTENT_IDENTIFIED,
    DiagnosisPhase.DATA_FETCHING: PublicSSEEventType.DATA_FETCH_STARTED,
    DiagnosisPhase.EVIDENCE_READY: PublicSSEEventType.RETRIEVAL_COMPLETED,
    DiagnosisPhase.NEED_USER_INPUT: PublicSSEEventType.NEED_USER_INPUT,
    DiagnosisPhase.DRAFT_READY: PublicSSEEventType.DRAFT_GENERATED,
    DiagnosisPhase.REVIEWING: PublicSSEEventType.DRAFT_GENERATED,
    DiagnosisPhase.COMPLETED: PublicSSEEventType.COMPLETED,
    DiagnosisPhase.FAILED: PublicSSEEventType.COMPLETED,
}


class PublicSSEEvent(StrictModel):
    event_id: str
    sequence: int = Field(ge=1)
    event_type: PublicSSEEventType
    event_version: int = Field(ge=1)
    session_id: str
    run_id: str
    trace_id: str
    acceptance_run_id: str
    phase: DiagnosisPhase
    occurred_at: UTCDateTime
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def phase_matches_event(self) -> PublicSSEEvent:
        if PHASE_EVENT_TYPES[self.phase] is not self.event_type:
            raise ValueError("public event_type does not match diagnosis phase")
        return self


class EventEnvelope(StrictModel):
    event_id: str
    event_type: str
    event_version: int = Field(ge=1)
    occurred_at: UTCDateTime
    tenant_id: str
    trace_id: str
    acceptance_run_id: str
    aggregate_type: str
    aggregate_id: str
    revision: int = Field(ge=1)
    idempotency_key: str
    payload: dict[str, Any] = Field(default_factory=dict)
