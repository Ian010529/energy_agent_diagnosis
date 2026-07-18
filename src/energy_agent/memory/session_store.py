import json

from pydantic import ValidationError
from redis.asyncio import Redis

from energy_agent.contracts.diagnosis import SessionMemoryPayload
from energy_agent.core.errors import DependencyUnavailableError
from energy_agent.observability.tracing import Tracer


class RedisSessionStore:
    def __init__(self, client: Redis, ttl_seconds: int, tracer: Tracer) -> None:
        self.client = client
        self.ttl_seconds = ttl_seconds
        self.tracer = tracer

    @staticmethod
    def key(session_id: str) -> str:
        return f"diag:session:{session_id}"

    async def save(self, payload: SessionMemoryPayload) -> None:
        with self.tracer.start_span(
            "persistence.redis_session.save",
            trace_id=payload.trace_id,
            metadata={"session_id": payload.session_id},
        ):
            try:
                await self.client.set(
                    self.key(payload.session_id),
                    payload.model_dump_json(),
                    ex=self.ttl_seconds,
                )
            except Exception as exc:
                raise DependencyUnavailableError("Redis session write failed") from exc

    async def get(self, session_id: str, *, trace_id: str) -> SessionMemoryPayload | None:
        with self.tracer.start_span(
            "persistence.redis_session.get",
            trace_id=trace_id,
            metadata={"session_id": session_id},
        ):
            try:
                value = await self.client.get(self.key(session_id))
            except Exception as exc:
                raise DependencyUnavailableError("Redis session read failed") from exc
            if value is None:
                return None
            try:
                return SessionMemoryPayload.model_validate_json(value)
            except (ValidationError, json.JSONDecodeError) as exc:
                raise DependencyUnavailableError("Redis session payload is invalid") from exc

    async def update(self, payload: SessionMemoryPayload) -> None:
        await self.save(payload)

    async def delete(self, session_id: str, *, trace_id: str) -> bool:
        with self.tracer.start_span(
            "persistence.redis_session.delete",
            trace_id=trace_id,
            metadata={"session_id": session_id},
        ):
            try:
                return bool(await self.client.delete(self.key(session_id)))
            except Exception as exc:
                raise DependencyUnavailableError("Redis session delete failed") from exc

    async def ttl(self, session_id: str, *, trace_id: str) -> int:
        try:
            return int(await self.client.ttl(self.key(session_id)))
        except Exception as exc:
            raise DependencyUnavailableError("Redis TTL read failed") from exc
