from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DiagnosisPhase(StrEnum):
    INIT = "INIT"
    PLAN_READY = "PLAN_READY"
    DATA_FETCHING = "DATA_FETCHING"
    EVIDENCE_READY = "EVIDENCE_READY"
    NEED_USER_INPUT = "NEED_USER_INPUT"
    DRAFT_READY = "DRAFT_READY"
    REVIEWING = "REVIEWING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class SessionSource(StrEnum):
    ALARM = "alarm"
    CHAT = "chat"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class DiagnosisIntent(StrEnum):
    FAULT_DIAGNOSIS = "fault_diagnosis"
    KNOWLEDGE_QA = "knowledge_qa"
    HISTORY_TICKET_QUERY = "history_ticket_query"
    FOLLOWUP_CLARIFICATION = "followup_clarification"
