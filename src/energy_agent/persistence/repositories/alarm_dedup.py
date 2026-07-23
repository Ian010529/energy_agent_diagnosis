from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from energy_agent.contracts.common import DiagnosisPhase
from energy_agent.core.time import ensure_utc, utc_now
from energy_agent.persistence.models import (
    DiagnosisAlarmDedupModel,
    DiagnosisSessionModel,
)
from energy_agent.reliability.contracts import AlarmDedupHit
from energy_agent.reliability.dedup import alarm_dedup_key, normalize_alarm_category


class AlarmDedupRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        window_seconds: int,
    ) -> None:
        self.session_factory = session_factory
        self.window_seconds = window_seconds

    async def hit(self, device_id: str, alarm_category: str, alarm_id: str) -> AlarmDedupHit | None:
        key = alarm_dedup_key(device_id, alarm_category)
        now = utc_now()
        async with self.session_factory.begin() as session:
            result = await session.execute(
                select(DiagnosisAlarmDedupModel)
                .where(DiagnosisAlarmDedupModel.dedup_key == key)
                .with_for_update()
            )
            model = result.scalar_one_or_none()
            if model is None or ensure_utc(model.expires_at) <= now:
                return None
            diagnosis = await session.get(DiagnosisSessionModel, model.session_id)
            if diagnosis is None or diagnosis.phase == DiagnosisPhase.FAILED:
                return None
            model.last_seen_at = now
            model.expires_at = now + timedelta(seconds=self.window_seconds)
            model.hit_count += 1
            model.alarm_ids = sorted({*model.alarm_ids, alarm_id})
            model.updated_at = now
            return AlarmDedupHit(model.session_id, model.hit_count)

    async def register(
        self,
        *,
        device_id: str,
        alarm_category: str,
        alarm_id: str,
        session_id: str,
    ) -> None:
        key = alarm_dedup_key(device_id, alarm_category)
        now = utc_now()
        async with self.session_factory.begin() as session:
            model = await session.get(DiagnosisAlarmDedupModel, key)
            values = {
                "device_id": device_id,
                "alarm_category": normalize_alarm_category(alarm_category),
                "session_id": session_id,
                "alarm_ids": [alarm_id],
                "first_seen_at": now,
                "last_seen_at": now,
                "expires_at": now + timedelta(seconds=self.window_seconds),
                "hit_count": 1,
                "updated_at": now,
            }
            if model is None:
                session.add(
                    DiagnosisAlarmDedupModel(
                        dedup_key=key,
                        created_at=now,
                        **values,
                    )
                )
            else:
                for name, value in values.items():
                    setattr(model, name, value)
