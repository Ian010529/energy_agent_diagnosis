from typing import Protocol

from energy_agent.contracts.diagnosis import (
    CreateSessionRequest,
    CreateSessionResponse,
    DiagnosisResponse,
)
from energy_agent.core.context import ActorContext


class SessionOperations(Protocol):
    async def create_session(
        self,
        payload: CreateSessionRequest,
        idempotency_key: str | None,
        actor: ActorContext | None = None,
    ) -> CreateSessionResponse: ...

    async def get_session(self, session_id: str) -> DiagnosisResponse: ...


class SessionService:
    def __init__(self, operations: SessionOperations) -> None:
        self.operations = operations

    async def create(
        self,
        payload: CreateSessionRequest,
        idempotency_key: str | None,
        actor: ActorContext | None = None,
    ) -> CreateSessionResponse:
        return await self.operations.create_session(payload, idempotency_key, actor)

    async def get(self, session_id: str) -> DiagnosisResponse:
        return await self.operations.get_session(session_id)
