from hashlib import sha256

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from energy_agent.core.time import ensure_utc, utc_now
from energy_agent.persistence.models import (
    DiagnosisSessionModel,
    DiagnosisTimelineEventModel,
)
from energy_agent.timeline.contracts import TimelineEventCreate, TimelineEventRecord


def timeline_event_id(session_id: str, event_type: str, key: str) -> str:
    return sha256(f"{session_id}:{event_type}:{key}".encode()).hexdigest()


class TimelineRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    @staticmethod
    def _record(model: DiagnosisTimelineEventModel) -> TimelineEventRecord:
        return TimelineEventRecord(
            id=model.id,
            event_id=model.event_id,
            session_id=model.session_id,
            run_id=model.run_id,
            sequence=model.sequence,
            event_type=model.event_type,
            actor_id=model.actor_id,
            actor_role=model.actor_role,
            payload=model.payload,
            created_at=ensure_utc(model.created_at),
        )

    async def append(self, payload: TimelineEventCreate) -> TimelineEventRecord:
        async with self.session_factory.begin() as session:
            existing = (
                await session.execute(
                    select(DiagnosisTimelineEventModel).where(
                        DiagnosisTimelineEventModel.event_id == payload.event_id
                    )
                )
            ).scalar_one_or_none()
            if existing:
                return self._record(existing)
            await session.execute(
                select(DiagnosisSessionModel.id)
                .where(DiagnosisSessionModel.id == payload.session_id)
                .with_for_update()
            )
            sequence = (
                int(
                    (
                        await session.execute(
                            select(
                                func.coalesce(func.max(DiagnosisTimelineEventModel.sequence), 0)
                            ).where(DiagnosisTimelineEventModel.session_id == payload.session_id)
                        )
                    ).scalar_one()
                )
                + 1
            )
            model = DiagnosisTimelineEventModel(
                **payload.model_dump(mode="json"),
                sequence=sequence,
                created_at=utc_now(),
            )
            session.add(model)
            await session.flush()
        return self._record(model)

    async def list(self, session_id: str) -> list[TimelineEventRecord]:
        async with self.session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(DiagnosisTimelineEventModel)
                        .where(DiagnosisTimelineEventModel.session_id == session_id)
                        .order_by(DiagnosisTimelineEventModel.sequence)
                    )
                )
                .scalars()
                .all()
            )
        return [self._record(row) for row in rows]
