from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from energy_agent.core.context import ActorContext
from energy_agent.core.errors import DependencyUnavailableError
from energy_agent.core.time import utc_now
from energy_agent.observability.redaction import redact
from energy_agent.observability.tracing import Tracer
from energy_agent.persistence.models import AuditEventModel


class AuditRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], tracer: Tracer) -> None:
        self.session_factory = session_factory
        self.tracer = tracer

    async def write(
        self,
        *,
        actor: ActorContext,
        action: str,
        resource_type: str,
        resource_id: str,
        trace_id: str,
        outcome: str = "succeeded",
        session_id: str | None = None,
        case_id: str | None = None,
        snapshot: dict[str, Any] | None = None,
    ) -> None:
        safe = redact(snapshot or {})
        if not isinstance(safe, dict):
            safe = {}
        with self.tracer.start_span(
            "audit.write",
            trace_id=trace_id,
            metadata={"action": action, "resource_type": resource_type},
        ):
            try:
                async with self.session_factory.begin() as session:
                    session.add(
                        AuditEventModel(
                            actor_id=actor.actor_id,
                            actor_role=actor.actor_role,
                            action=action,
                            resource_type=resource_type,
                            resource_id=resource_id,
                            session_id=session_id,
                            case_id=case_id,
                            trace_id=trace_id,
                            outcome=outcome,
                            safe_snapshot=safe,
                            created_at=utc_now(),
                        )
                    )
            except Exception as exc:
                raise DependencyUnavailableError("Audit write failed") from exc
