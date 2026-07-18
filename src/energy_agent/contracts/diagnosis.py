from datetime import datetime

from energy_agent.contracts.common import (
    DiagnosisPhase,
    RiskLevel,
    SessionSource,
    StrictModel,
)


class DiagnosisSessionCreate(StrictModel):
    id: str
    source: SessionSource
    site_id: str | None = None
    device_id: str | None = None
    alarm_id: str | None = None
    alarm_name: str | None = None
    phase: DiagnosisPhase = DiagnosisPhase.INIT
    final_summary: str | None = None
    risk_level: RiskLevel = RiskLevel.UNKNOWN
    trace_id: str
    run_id: str


class DiagnosisSessionRecord(DiagnosisSessionCreate):
    created_at: datetime
    updated_at: datetime


class DiagnosisSessionUpdate(StrictModel):
    phase: DiagnosisPhase | None = None
    final_summary: str | None = None
    risk_level: RiskLevel | None = None
    run_id: str | None = None


class StepLogCreate(StrictModel):
    session_id: str
    run_id: str
    trace_id: str
    step_name: str
    step_status: str
    input_snapshot: object | None = None
    output_snapshot: object | None = None
    error_code: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    duration_ms: int | None = None


class StepLogRecord(StepLogCreate):
    id: int


class SessionMemoryPayload(StrictModel):
    session_id: str
    phase: DiagnosisPhase
    run_id: str
    trace_id: str
    updated_at: datetime
    device_context: dict[str, str] | None = None
    alarm_context: dict[str, str] | None = None
    evidence_refs: list[str] = []
    clarification_questions: list[str] = []
    final_summary: str | None = None
    risk_level: RiskLevel = RiskLevel.UNKNOWN
