from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from energy_agent.contracts.common import StrictModel


class DiagnosisReviewResult(StrEnum):
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    NEEDS_MORE_INFO = "needs_more_info"


class CaseStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DISABLED = "DISABLED"
    SUPERSEDED = "SUPERSEDED"


class CaseIndexStatus(StrEnum):
    PENDING = "PENDING"
    INDEXED = "INDEXED"
    FAILED = "FAILED"
    TOMBSTONED = "TOMBSTONED"


class DiagnosisReviewRequest(StrictModel):
    review_result: DiagnosisReviewResult
    root_cause: str | None = None
    resolution_steps: list[str] = Field(default_factory=list)
    comments: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    source_ticket_id: str | None = None
    override_reason: str | None = None
    requested_questions: list[str] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def validate_decision(self) -> "DiagnosisReviewRequest":
        if self.review_result == DiagnosisReviewResult.CONFIRMED and (
            not self.root_cause or not self.resolution_steps or not self.evidence_refs
        ):
            raise ValueError(
                "confirmed review requires root_cause, resolution_steps and evidence_refs"
            )
        if self.review_result == DiagnosisReviewResult.REJECTED and not self.comments:
            raise ValueError("rejected review requires comments")
        if self.review_result == DiagnosisReviewResult.NEEDS_MORE_INFO and not (
            self.comments or self.requested_questions
        ):
            raise ValueError("needs_more_info requires comments or requested_questions")
        return self


class DiagnosisReviewResponse(StrictModel):
    review_id: str
    session_id: str
    run_id: str
    review_result: DiagnosisReviewResult
    case_id: str | None = None
    case_status: CaseStatus | None = None
    trace_id: str
    created_at: datetime


class DiagnosisCase(StrictModel):
    case_id: str
    source_session_id: str
    source_run_id: str
    source_review_id: str
    source_ticket_id: str | None = None
    device_type: str | None = None
    device_model: str | None = None
    manufacturer: str | None = None
    alarm_name: str | None = None
    symptom_summary: str | None = None
    timeseries_features: str | None = None
    root_cause: str
    resolution_steps: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    review_status: CaseStatus = CaseStatus.DRAFT
    reviewer: str | None = None
    review_comment: str | None = None
    case_version: int = Field(ge=1)
    embedding_text: str | None = None
    index_status: CaseIndexStatus = CaseIndexStatus.PENDING
    index_error_code: str | None = None
    is_active: bool = False
    supersedes_case_id: str | None = None
    created_by: str
    created_at: datetime
    updated_at: datetime


class CasePatchRequest(StrictModel):
    device_type: str | None = None
    device_model: str | None = None
    manufacturer: str | None = None
    alarm_name: str | None = None
    symptom_summary: str | None = None
    timeseries_features: str | None = None
    root_cause: str | None = None
    resolution_steps: list[str] | None = None
    safety_notes: list[str] | None = None
    evidence_refs: list[str] | None = None


class CaseReviewRequest(StrictModel):
    decision: str
    comment: str | None = None

    @model_validator(mode="after")
    def validate_decision(self) -> "CaseReviewRequest":
        if self.decision not in {"approve", "reject"}:
            raise ValueError("decision must be approve or reject")
        if self.decision == "reject" and not self.comment:
            raise ValueError("reject requires comment")
        return self


class CaseDisableRequest(StrictModel):
    reason: str = Field(min_length=1)


class CaseRevisionRequest(CasePatchRequest):
    submit_for_review: bool = False


class CaseListResponse(StrictModel):
    items: list[DiagnosisCase]
    total: int


class CaseReviewEvent(StrictModel):
    id: int
    case_id: str
    actor_id: str
    actor_role: str
    action: str
    from_status: CaseStatus | None = None
    to_status: CaseStatus
    comment: str | None = None
    trace_id: str
    created_at: datetime
