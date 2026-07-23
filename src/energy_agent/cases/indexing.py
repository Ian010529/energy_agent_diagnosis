from energy_agent.cases.application import CaseApplicationService
from energy_agent.contracts.cases import DiagnosisCase
from energy_agent.core.context import ActorContext


class CaseIndexCoordinator:
    def __init__(self, application: CaseApplicationService) -> None:
        self.application = application

    async def reindex(
        self, case_id: str, actor: ActorContext, idempotency_key: str | None
    ) -> DiagnosisCase:
        return await self.application.reindex(case_id, actor, idempotency_key)
