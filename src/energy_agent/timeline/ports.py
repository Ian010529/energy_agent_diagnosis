from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from energy_agent.contracts.cases import DiagnosisCase
from energy_agent.contracts.diagnosis import (
    DiagnosisResultRecord,
    DiagnosisSessionRecord,
    StepLogRecord,
)
from energy_agent.core.context import ActorContext
from energy_agent.timeline.contracts import (
    TimelineEventCreate,
    TimelineEventRecord,
    TimelineEventType,
)


class TimelineRepositoryPort(Protocol):
    async def append(self, payload: TimelineEventCreate) -> TimelineEventRecord: ...

    async def list(self, session_id: str) -> list[TimelineEventRecord]: ...


class TimelineSessionPort(Protocol):
    async def get(self, session_id: str, *, trace_id: str) -> DiagnosisSessionRecord | None: ...


class TimelineStepPort(Protocol):
    async def list_by_session(self, session_id: str, *, trace_id: str) -> list[StepLogRecord]: ...


class TimelineResultPort(Protocol):
    async def latest(self, session_id: str) -> DiagnosisResultRecord | None: ...


class TimelineReviewRecord(Protocol):
    review_id: str
    run_id: str
    review_result: str
    comments: str | None
    evidence_refs: list[str]
    created_at: datetime


class TimelineReviewPort(Protocol):
    async def list_by_session(self, session_id: str) -> Sequence[TimelineReviewRecord]: ...


class TimelineCasePort(Protocol):
    async def list_by_session(self, session_id: str) -> list[DiagnosisCase]: ...


class TimelineWriter(Protocol):
    def create(
        self,
        session_id: str,
        event_type: TimelineEventType,
        key: str,
        *,
        run_id: str | None = None,
        actor: ActorContext | None = None,
        payload: dict[str, object] | None = None,
    ) -> TimelineEventCreate: ...

    async def append(
        self,
        session_id: str,
        event_type: TimelineEventType,
        key: str,
        *,
        run_id: str | None = None,
        actor: ActorContext | None = None,
        payload: dict[str, object] | None = None,
    ) -> None: ...
