from datetime import datetime
from enum import StrEnum
from hashlib import sha256

from pydantic import Field

from energy_agent.contracts.common import StrictModel


def timeline_event_id(session_id: str, event_type: str, key: str) -> str:
    return sha256(f"{session_id}:{event_type}:{key}".encode()).hexdigest()


class TimelineEventType(StrEnum):
    USER_MESSAGE = "user_message"
    CLARIFICATION_QUESTION = "clarification_question"
    CLARIFICATION_ANSWER = "clarification_answer"
    DIAGNOSIS_RESULT = "diagnosis_result"
    REVIEW_SUBMITTED = "review_submitted"
    CASE_CREATED = "case_created"


class TimelineEventCreate(StrictModel):
    event_id: str
    session_id: str
    run_id: str | None = None
    event_type: TimelineEventType
    actor_id: str | None = None
    actor_role: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)


class TimelineEventRecord(TimelineEventCreate):
    id: int
    sequence: int
    created_at: datetime


class TimelineItem(StrictModel):
    timeline_id: str
    sequence: int
    kind: str
    run_id: str | None = None
    timestamp: datetime
    status: str | None = None
    title: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)


class TimelineResponse(StrictModel):
    session_id: str
    history_complete: bool
    items: list[TimelineItem]
