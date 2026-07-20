from enum import StrEnum

from pydantic import Field

from energy_agent.contracts.common import RiskLevel, StrictModel


class ActionExecutionStatus(StrEnum):
    NOT_EXECUTED = "not_executed"


class RecommendedAction(StrictModel):
    action_id: str
    description: str
    risk_level: RiskLevel
    requires_human_confirmation: bool
    required_role: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    execution_status: ActionExecutionStatus = ActionExecutionStatus.NOT_EXECUTED


class GuardrailStatus(StrEnum):
    PASSED = "PASSED"
    PASSED_WITH_WARNINGS = "PASSED_WITH_WARNINGS"
    NEED_USER_INPUT = "NEED_USER_INPUT"
    BLOCKED = "BLOCKED"


class GuardrailDecision(StrictModel):
    status: GuardrailStatus
    violations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW
    requires_human_confirmation: bool = False
    blocked_actions: list[str] = Field(default_factory=list)
    checked_evidence_refs: list[str] = Field(default_factory=list)
    decision_version: str = "guardrail.v1"
