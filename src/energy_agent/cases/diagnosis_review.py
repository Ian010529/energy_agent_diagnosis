from energy_agent.cases.application import CaseApplicationService
from energy_agent.contracts.cases import DiagnosisReviewRequest, DiagnosisReviewResponse
from energy_agent.core.context import ActorContext


class DiagnosisReviewService:
    def __init__(self, application: CaseApplicationService) -> None:
        self.application = application

    async def review(
        self,
        session_id: str,
        payload: DiagnosisReviewRequest,
        actor: ActorContext,
        idempotency_key: str | None,
    ) -> DiagnosisReviewResponse:
        return await self.application.review_diagnosis(session_id, payload, actor, idempotency_key)
