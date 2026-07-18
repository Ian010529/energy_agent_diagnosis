from enum import StrEnum

from energy_agent.contracts.common import StrictModel


class SSEEventType(StrEnum):
    INTENT_IDENTIFIED = "intent_identified"
    DATA_FETCH_STARTED = "data_fetch_started"
    RETRIEVAL_COMPLETED = "retrieval_completed"
    NEED_USER_INPUT = "need_user_input"
    DRAFT_GENERATED = "draft_generated"
    COMPLETED = "completed"


class SSEEvent(StrictModel):
    event: SSEEventType
    session_id: str
    run_id: str
    payload: dict[str, object]
