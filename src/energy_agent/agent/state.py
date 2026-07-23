from datetime import datetime

from pydantic import Field, model_validator

from energy_agent.contracts.common import (
    DiagnosisIntent,
    DiagnosisPhase,
    RiskLevel,
    SessionSource,
    StrictModel,
)
from energy_agent.contracts.diagnosis_components import (
    AlarmContext,
    CandidateCause,
    ClarificationQuestion,
    DeviceContext,
    Evidence,
    PlanStep,
    TimeWindow,
    ToolResultSummary,
    UserFeedback,
)
from energy_agent.core.errors import InvalidStateTransitionError
from energy_agent.core.time import utc_now
from energy_agent.guardrails.contracts import GuardrailDecision, RecommendedAction

__all__ = [
    "AlarmContext",
    "CandidateCause",
    "ClarificationQuestion",
    "DeviceContext",
    "DiagnosisState",
    "Evidence",
    "PlanStep",
    "TimeWindow",
    "ToolResultSummary",
    "UserFeedback",
    "transition_state",
]


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
    diagnosis_template_version: str | None = None
    alarm_category: str | None = None
    template_route_basis: str | None = None
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
    recommended_actions: list[RecommendedAction] = Field(default_factory=list)
    guardrail_decision: GuardrailDecision | None = None
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
