from datetime import datetime

from pydantic import Field, model_validator

from energy_agent.contracts.common import StrictModel


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
    has_usable_data: bool = False
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
    need_manual_confirmation: bool = False
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
