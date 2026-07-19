from datetime import datetime

from pydantic import Field, model_validator

from energy_agent.agent.state import CandidateCause, ClarificationQuestion, Evidence, PlanStep
from energy_agent.contracts.common import (
    DiagnosisIntent,
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
    created_by: str | None = None
    latest_review_status: str | None = None


class DiagnosisSessionRecord(DiagnosisSessionCreate):
    created_at: datetime
    updated_at: datetime


class DiagnosisRunCreate(StrictModel):
    id: str
    session_id: str
    trace_id: str
    idempotency_key: str | None = None
    request_hash: str
    phase: DiagnosisPhase = DiagnosisPhase.INIT
    status: str = "running"
    parent_run_id: str | None = None
    run_type: str = "diagnosis"
    diagnosis_template_id: str | None = None
    diagnosis_template_version: str | None = None
    alarm_category: str | None = None


class DiagnosisRunRecord(DiagnosisRunCreate):
    started_at: datetime
    ended_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class StructuredDiagnosisResult(StrictModel):
    summary: str
    candidate_causes: list[CandidateCause] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    inspection_steps: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    recommend_ticket: bool = False
    risk_level: RiskLevel = RiskLevel.UNKNOWN
    warnings: list[str] = Field(default_factory=list)
    degraded_components: list[str] = Field(default_factory=list)


class DiagnosisResultCreate(StructuredDiagnosisResult):
    run_id: str
    session_id: str


class DiagnosisResultRecord(DiagnosisResultCreate):
    created_at: datetime
    updated_at: datetime


class CreateSessionRequest(StrictModel):
    source: SessionSource
    site_id: str | None = None
    device_id: str | None = None
    alarm_id: str | None = None
    alarm_name: str | None = None

    @model_validator(mode="after")
    def validate_alarm_source(self) -> "CreateSessionRequest":
        if self.source == SessionSource.ALARM and not (self.device_id and self.alarm_id):
            raise ValueError("alarm source requires device_id and alarm_id")
        return self


class CreateSessionResponse(StrictModel):
    session_id: str
    run_id: str
    phase: DiagnosisPhase
    trace_id: str


class ClarificationAnswer(StrictModel):
    question_id: str
    answer: str


class DiagnosisChatRequest(StrictModel):
    session_id: str
    message: str
    clarification_answers: list[ClarificationAnswer] = Field(default_factory=list)
    expected_memory_revision: int | None = None
    followup_mode: str | None = None


class SessionMessageRequest(StrictModel):
    message: str
    clarification_answers: list[ClarificationAnswer] = Field(default_factory=list)
    expected_memory_revision: int | None = None
    followup_mode: str | None = None


class DiagnosisResponse(StrictModel):
    session_id: str
    run_id: str
    trace_id: str
    phase: DiagnosisPhase
    intent: DiagnosisIntent | None = None
    result: StructuredDiagnosisResult | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    tool_summaries: list[dict[str, object]] = Field(default_factory=list)
    clarification_questions: list[ClarificationQuestion] = Field(default_factory=list)
    degraded_components: list[str] = Field(default_factory=list)
    memory_revision: int | None = None
    review_status: str | None = None
    case_id: str | None = None
    case_status: str | None = None


class DiagnosisSessionUpdate(StrictModel):
    phase: DiagnosisPhase | None = None
    final_summary: str | None = None
    risk_level: RiskLevel | None = None
    run_id: str | None = None
    latest_review_status: str | None = None


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
    device_context: dict[str, object] | None = None
    alarm_context: dict[str, object] | None = None
    intent: DiagnosisIntent | None = None
    diagnosis_template_id: str | None = None
    diagnosis_template_version: str | None = None
    alarm_category: str | None = None
    plan: list[PlanStep] = Field(default_factory=list)
    tool_summaries: list[dict[str, object]] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    candidate_causes: list[CandidateCause] = Field(default_factory=list)
    clarification_questions: list[ClarificationQuestion] = Field(default_factory=list)
    clarification_answers: list[ClarificationAnswer] = Field(default_factory=list)
    final_result: StructuredDiagnosisResult | None = None
    degraded_components: list[str] = Field(default_factory=list)
    prompt_version: str = "diag.response_generator.v1.0"
    final_summary: str | None = None
    risk_level: RiskLevel = RiskLevel.UNKNOWN
    memory_revision: int = 1
    parent_run_id: str | None = None
    time_window: dict[str, object] | None = None
    pending_question_ids: list[str] = Field(default_factory=list)
    resolved_question_ids: list[str] = Field(default_factory=list)
    user_feedback_history: list[ClarificationAnswer] = Field(default_factory=list)
    evidence_package_ids: list[str] = Field(default_factory=list)
    last_completed_node: str | None = None
    state_version: str = "phase4.v1"
