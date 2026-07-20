from typing import Literal

from pydantic import Field

from energy_agent.contracts.common import StrictModel

EvaluationSplit = Literal["calibration", "regression", "holdout"]


class RuntimeSample(StrictModel):
    sample_id: str
    dataset_id: str
    dataset_version: str
    split: EvaluationSplit
    template_id: str
    evidence_profile: str
    site_id: str
    device_id: str
    alarm_id: str
    alarm_name: str
    input_text: str
    scenario_kind: str
    dependency_mode: str
    available_source_ids: list[str] = Field(default_factory=list)
    trigger_time: str | None = None
    timeseries_window_ref: str | None = None


class GoldSample(StrictModel):
    sample_id: str
    dataset_version: str
    split: EvaluationSplit
    template_id: str
    device_id: str
    alarm_id: str
    canonical_root_cause_id: str
    accepted_root_cause_aliases: list[str]
    expected_escalation: bool
    expected_escalation_reasons: list[str] = Field(default_factory=list)
    expected_phase: str
    high_risk_expected: bool
    relevant_evidence: list[dict[str, object]] = Field(default_factory=list)
    relevant_source_ids: list[str] = Field(default_factory=list)
    required_evidence_types: list[str] = Field(default_factory=list)
    forbidden_source_ids: list[str] = Field(default_factory=list)
    forbidden_assertions: list[str] = Field(default_factory=list)


class EvaluationSample(StrictModel):
    runtime: RuntimeSample
    gold: GoldSample


class ToolAttempt(StrictModel):
    attempt_id: str
    status: str
    has_usable_data: bool = False


class PerSampleResult(StrictModel):
    sample_id: str
    split: EvaluationSplit
    template_id: str
    evidence_profile: str
    phase: str
    candidate_causes: list[str] = Field(default_factory=list)
    candidate_evidence_refs: list[list[str]] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_source_ids: list[str] = Field(default_factory=list)
    evidence_types: list[str] = Field(default_factory=list)
    tool_attempts: list[ToolAttempt] = Field(default_factory=list)
    escalated: bool = False
    first_event_latency_seconds: float | None = None
    duration_seconds: float
    high_risk_action_count: int = 0
    confirmed_high_risk_action_count: int = 0
    blocked_action_count: int = 0
    guardrail_status: str | None = None
    failure_category: str | None = None
    forbidden_assertion_count: int = 0
    prompt_injection_escaped: bool = False
    gold_leak_detected: bool = False
