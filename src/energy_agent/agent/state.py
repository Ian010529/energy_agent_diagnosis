from datetime import datetime

from pydantic import Field, model_validator

from energy_agent.contracts.common import (
    DiagnosisIntent,
    DiagnosisPhase,
    RiskLevel,
    SessionSource,
    StrictModel,
)
from energy_agent.core.errors import InvalidStateTransitionError
from energy_agent.core.time import utc_now


class DeviceContext(StrictModel):
    site_id: str | None = None
    device_id: str
    device_type: str | None = None
    device_model: str | None = None
    manufacturer: str | None = None


class AlarmContext(StrictModel):
    alarm_id: str
    alarm_name: str
    trigger_time: datetime | None = None


class TimeWindow(StrictModel):
    start_time: datetime
    end_time: datetime

    @model_validator(mode="after")
    def validate_order(self) -> "TimeWindow":
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be before end_time")
        return self


class PlanStep(StrictModel):
    step_id: str
    goal: str
    tool: str | None = None
    required: bool = True
    parameters: dict[str, object] = Field(default_factory=dict)


class ToolResultSummary(StrictModel):
    tool_name: str
    status: str
    result_ref: str | None = None
    summary: str | None = None


class Evidence(StrictModel):
    evidence_id: str
    source_type: str
    source_id: str
    summary: str
    citation: str
    verified: bool = False
    reliability: float = Field(ge=0, le=1)
    relevance: float = Field(ge=0, le=1)
    retrieval_score: float | None = Field(default=None, ge=0, le=1)
    source_reliability: float | None = Field(default=None, ge=0, le=1)
    verification_score: float | None = Field(default=None, ge=0, le=1)
    freshness_score: float | None = Field(default=None, ge=0, le=1)
    relevance_to_alarm: float | None = Field(default=None, ge=0, le=1)
    final_score: float | None = Field(default=None, ge=0, le=1)
    chunk_id: str | None = None
    package_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class CandidateCause(StrictModel):
    cause: str
    confidence: float = Field(ge=0, le=1)
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    need_manual_confirmation: bool = True


class ClarificationQuestion(StrictModel):
    question_id: str
    question: str
    reason: str
    expected_answer_type: str = "text"


class UserFeedback(StrictModel):
    question_id: str
    answer: str


class DiagnosisState(StrictModel):
    session_id: str
    run_id: str
    trace_id: str
    phase: DiagnosisPhase = DiagnosisPhase.INIT
    source: SessionSource
    user_message: str | None = None
    followup_mode: str | None = None
    memory_revision: int = 1
    parent_run_id: str | None = None
    intent: DiagnosisIntent | None = None
    diagnosis_template_id: str | None = None
    device_context: DeviceContext | None = None
    alarm_context: AlarmContext | None = None
    time_window: TimeWindow | None = None
    plan: list[PlanStep] = Field(default_factory=list)
    tool_results: list[ToolResultSummary] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    candidate_causes: list[CandidateCause] = Field(default_factory=list)
    clarification_questions: list[ClarificationQuestion] = Field(default_factory=list)
    user_feedback: list[UserFeedback] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.UNKNOWN
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    degraded_components: list[str] = Field(default_factory=list)
    final_response: dict[str, object] | None = None
    prompt_version: str = "diag.response_generator.v1.0"
    started_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_phase_requirements(self) -> "DiagnosisState":
        if self.phase == DiagnosisPhase.NEED_USER_INPUT and not self.clarification_questions:
            raise ValueError("NEED_USER_INPUT requires at least one clarification question")
        if self.phase == DiagnosisPhase.COMPLETED and not self.final_response:
            raise ValueError("COMPLETED requires a final response")
        return self


_ALLOWED_TRANSITIONS: dict[DiagnosisPhase, frozenset[DiagnosisPhase]] = {
    DiagnosisPhase.INIT: frozenset({DiagnosisPhase.PLAN_READY, DiagnosisPhase.FAILED}),
    DiagnosisPhase.PLAN_READY: frozenset(
        {DiagnosisPhase.DATA_FETCHING, DiagnosisPhase.NEED_USER_INPUT, DiagnosisPhase.FAILED}
    ),
    DiagnosisPhase.DATA_FETCHING: frozenset(
        {DiagnosisPhase.EVIDENCE_READY, DiagnosisPhase.NEED_USER_INPUT, DiagnosisPhase.FAILED}
    ),
    DiagnosisPhase.EVIDENCE_READY: frozenset(
        {DiagnosisPhase.NEED_USER_INPUT, DiagnosisPhase.DRAFT_READY, DiagnosisPhase.FAILED}
    ),
    DiagnosisPhase.NEED_USER_INPUT: frozenset(
        {
            DiagnosisPhase.PLAN_READY,
            DiagnosisPhase.DATA_FETCHING,
            DiagnosisPhase.EVIDENCE_READY,
            DiagnosisPhase.FAILED,
        }
    ),
    DiagnosisPhase.DRAFT_READY: frozenset({DiagnosisPhase.REVIEWING, DiagnosisPhase.FAILED}),
    DiagnosisPhase.REVIEWING: frozenset(
        {DiagnosisPhase.DRAFT_READY, DiagnosisPhase.COMPLETED, DiagnosisPhase.FAILED}
    ),
    DiagnosisPhase.COMPLETED: frozenset(),
    DiagnosisPhase.FAILED: frozenset(),
}


def transition_state(
    state: DiagnosisState, target: DiagnosisPhase, **updates: object
) -> DiagnosisState:
    if target not in _ALLOWED_TRANSITIONS[state.phase]:
        raise InvalidStateTransitionError(f"Cannot transition from {state.phase} to {target}")
    candidate = state.model_copy(
        update={"phase": target, "updated_at": utc_now(), **updates},
    )
    return DiagnosisState.model_validate(candidate.model_dump())
