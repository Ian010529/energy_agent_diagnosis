from energy_agent.cases.application import (
    CaseApplicationService,
    build_embedding_text,
    missing_case_fields,
)

__all__ = ["CaseService", "build_embedding_text", "missing_case_fields"]
from energy_agent.cases.diagnosis_review import DiagnosisReviewService
from energy_agent.cases.indexing import CaseIndexCoordinator
from energy_agent.cases.lifecycle import CaseLifecycleService
from energy_agent.cases.ports import (
    CaseAuditPort,
    CaseRepositoryPort,
    CaseResultPort,
    CaseSessionPort,
    CaseVectorPort,
    EmbeddingPort,
)
from energy_agent.cases.review_recorder import DiagnosisReviewRecorder
from energy_agent.contracts.cases import (
    CaseDisableRequest,
    CasePatchRequest,
    CaseReviewEvent,
    CaseReviewRequest,
    CaseRevisionRequest,
    DiagnosisCase,
    DiagnosisReviewRequest,
    DiagnosisReviewResponse,
)
from energy_agent.core.context import ActorContext
from energy_agent.observability.tracing import Tracer
from energy_agent.timeline.ports import TimelineWriter


class CaseService:
    """Stable API façade for review, lifecycle, and indexing application services."""

    def __init__(
        self,
        *,
        cases: CaseRepositoryPort,
        sessions: CaseSessionPort,
        results: CaseResultPort,
        audit: CaseAuditPort,
        review_recorder: DiagnosisReviewRecorder,
        tracer: Tracer,
        embedding: EmbeddingPort | None,
        milvus: CaseVectorPort | None,
        index_execution_mode: str = "sync",
        index_max_attempts: int = 3,
        timeline: TimelineWriter | None = None,
    ) -> None:
        application = CaseApplicationService(
            cases=cases,
            sessions=sessions,
            results=results,
            audit=audit,
            review_recorder=review_recorder,
            tracer=tracer,
            embedding=embedding,
            milvus=milvus,
            index_execution_mode=index_execution_mode,
            index_max_attempts=index_max_attempts,
            timeline=timeline,
        )
        self._reviews = DiagnosisReviewService(application)
        self._lifecycle = CaseLifecycleService(application)
        self._indexing = CaseIndexCoordinator(application)

    async def review_diagnosis(
        self,
        session_id: str,
        payload: DiagnosisReviewRequest,
        actor: ActorContext,
        idempotency_key: str | None,
    ) -> DiagnosisReviewResponse:
        return await self._reviews.review(session_id, payload, actor, idempotency_key)

    async def get(self, case_id: str) -> DiagnosisCase:
        return await self._lifecycle.get(case_id)

    async def list_cases(self, filters: dict[str, object]) -> list[DiagnosisCase]:
        return await self._lifecycle.list_cases(filters)

    async def list_case_page(
        self, filters: dict[str, object], *, limit: int, cursor: str | None, sort: str
    ) -> tuple[list[DiagnosisCase], int, str | None]:
        return await self._lifecycle.list_case_page(filters, limit=limit, cursor=cursor, sort=sort)

    async def patch(
        self, case_id: str, payload: CasePatchRequest, actor: ActorContext
    ) -> DiagnosisCase:
        return await self._lifecycle.patch(case_id, payload, actor)

    async def submit(
        self, case_id: str, actor: ActorContext, idempotency_key: str | None
    ) -> DiagnosisCase:
        return await self._lifecycle.submit(case_id, actor, idempotency_key)

    async def review_case(
        self,
        case_id: str,
        payload: CaseReviewRequest,
        actor: ActorContext,
        idempotency_key: str | None,
    ) -> DiagnosisCase:
        return await self._lifecycle.review_case(case_id, payload, actor, idempotency_key)

    async def disable(
        self,
        case_id: str,
        payload: CaseDisableRequest,
        actor: ActorContext,
        idempotency_key: str | None,
    ) -> DiagnosisCase:
        return await self._lifecycle.disable(case_id, payload, actor, idempotency_key)

    async def revision(
        self,
        case_id: str,
        payload: CaseRevisionRequest,
        actor: ActorContext,
        idempotency_key: str | None,
    ) -> DiagnosisCase:
        return await self._lifecycle.revision(case_id, payload, actor, idempotency_key)

    async def reindex(
        self, case_id: str, actor: ActorContext, idempotency_key: str | None
    ) -> DiagnosisCase:
        return await self._indexing.reindex(case_id, actor, idempotency_key)

    async def history(self, case_id: str) -> list[CaseReviewEvent]:
        return await self._lifecycle.history(case_id)
