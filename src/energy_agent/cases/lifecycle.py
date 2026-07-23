from energy_agent.cases.application import CaseApplicationService
from energy_agent.contracts.cases import (
    CaseDisableRequest,
    CasePatchRequest,
    CaseReviewEvent,
    CaseReviewRequest,
    CaseRevisionRequest,
    DiagnosisCase,
)
from energy_agent.core.context import ActorContext


class CaseLifecycleService:
    def __init__(self, application: CaseApplicationService) -> None:
        self.application = application

    async def get(self, case_id: str) -> DiagnosisCase:
        return await self.application.get(case_id)

    async def list_cases(self, filters: dict[str, object]) -> list[DiagnosisCase]:
        return await self.application.list_cases(filters)

    async def list_case_page(
        self, filters: dict[str, object], *, limit: int, cursor: str | None, sort: str
    ) -> tuple[list[DiagnosisCase], int, str | None]:
        return await self.application.list_case_page(filters, limit=limit, cursor=cursor, sort=sort)

    async def patch(
        self, case_id: str, payload: CasePatchRequest, actor: ActorContext
    ) -> DiagnosisCase:
        return await self.application.patch(case_id, payload, actor)

    async def submit(
        self, case_id: str, actor: ActorContext, idempotency_key: str | None
    ) -> DiagnosisCase:
        return await self.application.submit(case_id, actor, idempotency_key)

    async def review_case(
        self,
        case_id: str,
        payload: CaseReviewRequest,
        actor: ActorContext,
        idempotency_key: str | None,
    ) -> DiagnosisCase:
        return await self.application.review_case(case_id, payload, actor, idempotency_key)

    async def disable(
        self,
        case_id: str,
        payload: CaseDisableRequest,
        actor: ActorContext,
        idempotency_key: str | None,
    ) -> DiagnosisCase:
        return await self.application.disable(case_id, payload, actor, idempotency_key)

    async def revision(
        self,
        case_id: str,
        payload: CaseRevisionRequest,
        actor: ActorContext,
        idempotency_key: str | None,
    ) -> DiagnosisCase:
        return await self.application.revision(case_id, payload, actor, idempotency_key)

    async def history(self, case_id: str) -> list[CaseReviewEvent]:
        return await self.application.history(case_id)
