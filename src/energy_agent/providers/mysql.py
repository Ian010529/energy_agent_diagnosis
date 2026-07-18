from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from energy_agent.core.time import ensure_utc
from energy_agent.persistence.models import (
    AlarmEventModel,
    DeviceProfileModel,
    MaintenanceTicketModel,
    ManualChunkModel,
    ManualDocumentModel,
)


class MySQLDiagnosisProvider:
    provider_type = "real"

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def get_device(self, device_id: str) -> dict[str, object] | None:
        async with self.session_factory() as session:
            model = await session.get(DeviceProfileModel, device_id)
            if model is None:
                return None
            return {
                column.name: getattr(model, column.name)
                for column in DeviceProfileModel.__table__.columns
            }

    async def get_alarm(self, alarm_id: str, device_id: str | None) -> dict[str, object] | None:
        async with self.session_factory() as session:
            query = select(AlarmEventModel).where(AlarmEventModel.alarm_id == alarm_id)
            if device_id:
                query = query.where(AlarmEventModel.device_id == device_id)
            model = (await session.execute(query)).scalar_one_or_none()
            if model is None:
                return None
            data = {
                column.name: getattr(model, column.name)
                for column in AlarmEventModel.__table__.columns
            }
            data["trigger_time"] = ensure_utc(model.trigger_time)
            return data

    async def manual_candidates(
        self,
        filters: dict[str, object],
        *,
        effective_only: bool = True,
        strong_only: bool = False,
    ) -> list[dict[str, object]]:
        query = select(ManualChunkModel)
        for name in ("device_type", "device_model", "manufacturer", "alarm_name"):
            value = filters.get(name)
            if value:
                query = query.where(getattr(ManualChunkModel, name) == value)
        if effective_only:
            query = query.where(ManualChunkModel.effective.is_(True))
        if filters.get("doc_version"):
            query = query.where(ManualChunkModel.version == filters["doc_version"])
        section_types = filters.get("section_type")
        if isinstance(section_types, list) and section_types:
            query = query.where(ManualChunkModel.section_type.in_(section_types))
        if strong_only:
            query = query.join(
                ManualDocumentModel,
                (ManualDocumentModel.doc_id == ManualChunkModel.doc_id)
                & (ManualDocumentModel.version == ManualChunkModel.version),
            ).where(
                ManualDocumentModel.review_status == "APPROVED",
                ManualDocumentModel.effective.is_(True),
                ManualDocumentModel.index_status == "INDEXED",
            )
        async with self.session_factory() as session:
            rows = (await session.execute(query)).scalars().all()
        return [
            {
                column.name: getattr(row, column.name)
                for column in ManualChunkModel.__table__.columns
            }
            for row in rows
        ]

    async def ticket_candidates(
        self, filters: dict[str, object], *, verified_only: bool = True
    ) -> list[dict[str, object]]:
        query = select(MaintenanceTicketModel)
        for name in ("device_model", "alarm_name", "site_id"):
            value = filters.get(name)
            if value:
                query = query.where(getattr(MaintenanceTicketModel, name) == value)
        if verified_only:
            query = query.where(MaintenanceTicketModel.is_verified.is_(True))
        excluded = filters.get("exclude_ticket_ids")
        if isinstance(excluded, list) and excluded:
            query = query.where(MaintenanceTicketModel.ticket_id.not_in(excluded))
        async with self.session_factory() as session:
            rows = (await session.execute(query)).scalars().all()
        return [
            {
                column.name: getattr(row, column.name)
                for column in MaintenanceTicketModel.__table__.columns
            }
            for row in rows
        ]
