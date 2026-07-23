from dataclasses import dataclass
from typing import Any, Protocol

from energy_agent.contracts.cases import (
    CaseIndexStatus,
    CaseReviewEvent,
    CaseStatus,
    DiagnosisCase,
)
from energy_agent.contracts.diagnosis import (
    DiagnosisResultRecord,
    DiagnosisSessionRecord,
    DiagnosisSessionUpdate,
)
from energy_agent.core.context import ActorContext, ServiceActorContext
from energy_agent.indexing.contracts import IndexJobCreate


@dataclass(frozen=True, slots=True)
class CaseTransitionResult:
    case: DiagnosisCase
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class CaseIdempotencyRecord:
    request_hash: str
    comment: str | None = None


class CaseRepositoryPort(Protocol):
    async def create(self, values: dict[str, object]) -> DiagnosisCase: ...

    async def get(self, case_id: str) -> DiagnosisCase | None: ...

    async def get_by_review(self, review_id: str) -> DiagnosisCase | None: ...

    async def list_cases(self, filters: dict[str, object]) -> list[DiagnosisCase]: ...

    async def list_page(
        self,
        filters: dict[str, object],
        *,
        limit: int,
        cursor: str | None,
        sort: str,
    ) -> tuple[list[DiagnosisCase], int, str | None]: ...

    async def update_draft(
        self,
        case_id: str,
        values: dict[str, object],
        actor_id: str,
        *,
        privileged: bool,
    ) -> DiagnosisCase: ...

    async def transition(
        self,
        case_id: str,
        *,
        expected: CaseStatus,
        target: CaseStatus,
        actor_id: str,
        actor_role: str,
        action: str,
        trace_id: str,
        request_hash: str,
        idempotency_key: str | None,
        comment: str | None = None,
        updates: dict[str, object] | None = None,
        index_request: IndexJobCreate | None = None,
    ) -> CaseTransitionResult: ...

    async def queue_index(
        self,
        case_id: str,
        *,
        request: IndexJobCreate,
        actor_id: str,
        actor_role: str,
        action: str,
        trace_id: str,
        request_hash: str,
        idempotency_key: str | None,
    ) -> DiagnosisCase: ...

    async def find_idempotent_event(
        self, case_id: str, idempotency_key: str
    ) -> CaseIdempotencyRecord | None: ...

    async def append_event(
        self,
        *,
        case_id: str,
        actor_id: str,
        actor_role: str,
        action: str,
        from_status: CaseStatus,
        to_status: CaseStatus,
        comment: str | None,
        idempotency_key: str | None,
        request_hash: str,
        trace_id: str,
    ) -> None: ...

    async def set_index(
        self,
        case_id: str,
        status: CaseIndexStatus,
        *,
        error_code: str | None = None,
        embedding_text: str | None = None,
        active: bool | None = None,
    ) -> DiagnosisCase: ...

    async def next_version(self, session_id: str) -> int: ...

    async def history(self, case_id: str) -> list[CaseReviewEvent]: ...


class CaseSessionPort(Protocol):
    async def get(self, session_id: str, *, trace_id: str) -> DiagnosisSessionRecord | None: ...

    async def update(
        self, session_id: str, payload: DiagnosisSessionUpdate, *, trace_id: str
    ) -> DiagnosisSessionRecord: ...


class CaseResultPort(Protocol):
    async def latest(self, session_id: str) -> DiagnosisResultRecord | None: ...


class CaseAuditPort(Protocol):
    async def write(
        self,
        *,
        actor: ActorContext | ServiceActorContext,
        action: str,
        resource_type: str,
        resource_id: str,
        trace_id: str,
        outcome: str = "succeeded",
        session_id: str | None = None,
        case_id: str | None = None,
        snapshot: dict[str, Any] | None = None,
    ) -> None: ...


class EmbeddingPort(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class CaseVectorPort(Protocol):
    async def upsert(self, source: str, rows: list[dict[str, Any]]) -> None: ...

    async def delete(self, source: str, ids: list[str]) -> None: ...
