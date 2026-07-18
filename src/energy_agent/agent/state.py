from datetime import datetime

from pydantic import Field, model_validator

from energy_agent.contracts.common import (
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
    name: str
    purpose: str


class ToolResultSummary(StrictModel):
    tool_name: str
    status: str
    result_ref: str | None = None
    summary: str | None = None


class EvidenceSummary(StrictModel):
    evidence_id: str
    source_type: str
    summary: str


class CandidateCause(StrictModel):
    cause: str
    confidence: float = Field(ge=0, le=1)
    evidence_refs: list[str] = Field(default_factory=list)


class UserFeedback(StrictModel):
    question: str
    answer: str


class DiagnosisState(StrictModel):
    session_id: str
    run_id: str
    trace_id: str
    phase: DiagnosisPhase = DiagnosisPhase.INIT
    source: SessionSource
    user_message: str | None = None
    device_context: DeviceContext | None = None
    alarm_context: AlarmContext | None = None
    time_window: TimeWindow | None = None
    plan: list[PlanStep] = Field(default_factory=list)
    tool_results: list[ToolResultSummary] = Field(default_factory=list)
    evidence: list[EvidenceSummary] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    candidate_causes: list[CandidateCause] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    user_feedback: list[UserFeedback] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.UNKNOWN
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    final_response: str | None = None
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
        {DiagnosisPhase.DATA_FETCHING, DiagnosisPhase.EVIDENCE_READY, DiagnosisPhase.FAILED}
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
