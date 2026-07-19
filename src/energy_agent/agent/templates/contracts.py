from pydantic import Field

from energy_agent.contracts.common import StrictModel


class CandidateRule(StrictModel):
    cause: str
    evidence_terms: list[str] = Field(min_length=1)
    missing_information: list[str] = Field(default_factory=list)
    base_confidence: float = Field(default=0.55, ge=0, le=0.8)


class TemplateGraphRelation(StrictModel):
    fault_cause: str
    component: str
    actions: list[str] = Field(default_factory=list)


class DiagnosisTemplate(StrictModel):
    template_id: str
    template_version: str
    device_type: str
    device_aliases: list[str]
    alarm_category: str
    alarm_patterns: list[str]
    alarm_aliases: list[str]
    measurements: list[str] = Field(min_length=1)
    metrics: list[str] = Field(min_length=1)
    default_window_minutes: int = Field(default=30, ge=1, le=1440)
    plan_steps: list[str] = Field(min_length=1)
    candidate_rules: list[CandidateRule] = Field(min_length=1)
    clarification_rules: list[str] = Field(min_length=1)
    inspection_steps: list[str] = Field(min_length=1)
    safety_notes: list[str] = Field(min_length=1)
    graph_relations: list[TemplateGraphRelation] = Field(default_factory=list)
