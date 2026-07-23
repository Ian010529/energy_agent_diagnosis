import base64
import binascii
from datetime import UTC, datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from energy_agent.catalog.contracts import (
    AlarmRecord,
    DeviceItem,
    DiagnosisSessionItem,
    SiteItem,
)
from energy_agent.core.errors import InvalidRequestError, ResourceNotFoundError
from energy_agent.core.time import ensure_utc
from energy_agent.persistence.models import (
    AlarmEventModel,
    DeviceProfileModel,
    DiagnosisRunModel,
    DiagnosisSessionModel,
)


def encode_cursor(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def decode_cursor(value: str | None) -> str | None:
    if not value:
        return None
    try:
        decoded = base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        ).decode()
        if not decoded:
            raise ValueError("empty cursor")
        return decoded
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise InvalidRequestError("Cursor is invalid") from exc


def query_datetime(value: object) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return parsed.astimezone(UTC).replace(tzinfo=None) if parsed.tzinfo is not None else parsed


class CatalogRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def sites(self) -> list[SiteItem]:
        async with self.session_factory() as session:
            devices = (
                await session.execute(
                    select(
                        DeviceProfileModel.site_id,
                        DeviceProfileModel.device_type,
                        DeviceProfileModel.status,
                        func.count(),
                    ).group_by(
                        DeviceProfileModel.site_id,
                        DeviceProfileModel.device_type,
                        DeviceProfileModel.status,
                    )
                )
            ).all()
            alarm_rows = (
                await session.execute(
                    select(AlarmEventModel.site_id, func.count())
                    .where(AlarmEventModel.status.not_in(["CLOSED", "CLEARED", "RESOLVED"]))
                    .group_by(AlarmEventModel.site_id)
                )
            ).all()
            alarms: dict[str, int] = {site_id: count for site_id, count in alarm_rows}
        totals: dict[str, int] = {}
        device_type_counts: dict[str, dict[str, int]] = {}
        status_counts: dict[str, dict[str, int]] = {}
        for site_id, device_type, status, count in devices:
            totals[site_id] = totals.get(site_id, 0) + count
            device_types = device_type_counts.setdefault(site_id, {})
            statuses = status_counts.setdefault(site_id, {})
            device_types[device_type] = device_types.get(device_type, 0) + count
            statuses[status] = statuses.get(status, 0) + count
        return [
            SiteItem(
                site_id=site_id,
                display_name=site_id,
                device_count=totals[site_id],
                active_alarm_count=int(alarms.get(site_id, 0)),
                device_type_counts=device_type_counts[site_id],
                status_counts=status_counts[site_id],
            )
            for site_id in sorted(totals)
        ]

    async def devices(
        self, filters: dict[str, object], limit: int, cursor: str | None
    ) -> tuple[list[DeviceItem], str | None]:
        alarm_count = (
            select(func.count(AlarmEventModel.alarm_id))
            .where(AlarmEventModel.device_id == DeviceProfileModel.device_id)
            .correlate(DeviceProfileModel)
            .scalar_subquery()
        )
        query = select(DeviceProfileModel, alarm_count.label("alarm_count"))
        for name in (
            "site_id",
            "device_type",
            "device_model",
            "manufacturer",
            "status",
        ):
            if filters.get(name):
                query = query.where(getattr(DeviceProfileModel, name) == filters[name])
        q = str(filters.get("q") or "").strip()
        if q:
            like = f"%{q}%"
            query = query.where(
                or_(
                    DeviceProfileModel.device_id.like(like),
                    DeviceProfileModel.device_model.like(like),
                    DeviceProfileModel.manufacturer.like(like),
                    DeviceProfileModel.location.like(like),
                )
            )
        after = decode_cursor(cursor)
        if after:
            query = query.where(DeviceProfileModel.device_id > after)
        query = query.order_by(DeviceProfileModel.device_id).limit(limit + 1)
        async with self.session_factory() as session:
            rows = (await session.execute(query)).all()
        has_more = len(rows) > limit
        rows = rows[:limit]
        items = [
            DeviceItem(
                **{
                    **{
                        column.name: getattr(model, column.name)
                        for column in DeviceProfileModel.__table__.columns
                    },
                    "commission_time": ensure_utc(model.commission_time)
                    if model.commission_time
                    else None,
                    "latest_alarm_count": count,
                }
            )
            for model, count in rows
        ]
        return items, encode_cursor(items[-1].device_id) if has_more and items else None

    async def device(self, device_id: str) -> DeviceItem:
        alarm_count = (
            select(func.count(AlarmEventModel.alarm_id))
            .where(AlarmEventModel.device_id == DeviceProfileModel.device_id)
            .correlate(DeviceProfileModel)
            .scalar_subquery()
        )
        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(DeviceProfileModel, alarm_count.label("alarm_count")).where(
                        DeviceProfileModel.device_id == device_id
                    )
                )
            ).one_or_none()
        if not row:
            raise ResourceNotFoundError("Device not found")
        model, count = row
        return DeviceItem(
            **{
                **{
                    column.name: getattr(model, column.name)
                    for column in DeviceProfileModel.__table__.columns
                },
                "commission_time": ensure_utc(model.commission_time)
                if model.commission_time
                else None,
                "latest_alarm_count": count,
            }
        )

    async def alarms(
        self, filters: dict[str, object], limit: int, cursor: str | None
    ) -> tuple[list[AlarmRecord], str | None]:
        query = select(AlarmEventModel, DeviceProfileModel.device_type).join(
            DeviceProfileModel,
            DeviceProfileModel.device_id == AlarmEventModel.device_id,
        )
        for name in ("site_id", "device_id", "alarm_level", "status", "source_system"):
            if filters.get(name):
                query = query.where(getattr(AlarmEventModel, name) == filters[name])
        if filters.get("from_time"):
            query = query.where(
                AlarmEventModel.trigger_time >= query_datetime(filters["from_time"])
            )
        if filters.get("to_time"):
            query = query.where(AlarmEventModel.trigger_time <= query_datetime(filters["to_time"]))
        q = str(filters.get("q") or "").strip()
        if q:
            like = f"%{q}%"
            query = query.where(
                or_(
                    AlarmEventModel.alarm_id.like(like),
                    AlarmEventModel.alarm_name.like(like),
                )
            )
        cursor_time: datetime | None = None
        cursor_id: str | None = None
        after = decode_cursor(cursor)
        if after:
            parts = after.split("|", 1)
            if len(parts) != 2:
                raise InvalidRequestError("Cursor is invalid")
            try:
                cursor_time = query_datetime(parts[0])
            except ValueError as exc:
                raise InvalidRequestError("Cursor is invalid") from exc
            cursor_id = parts[1]
        if cursor_time is not None and cursor_id is not None:
            query = query.where(
                or_(
                    AlarmEventModel.trigger_time < cursor_time,
                    and_(
                        AlarmEventModel.trigger_time == cursor_time,
                        AlarmEventModel.alarm_id > cursor_id,
                    ),
                )
            )
        query = query.order_by(AlarmEventModel.trigger_time.desc(), AlarmEventModel.alarm_id)
        async with self.session_factory() as session:
            rows = (await session.execute(query.limit(limit + 1))).all()
        has_more = len(rows) > limit
        rows = rows[:limit]
        mapped = [
            AlarmRecord(
                **{
                    column.name: getattr(model, column.name)
                    for column in AlarmEventModel.__table__.columns
                    if column.name != "trigger_time"
                },
                device_type=device_type,
                trigger_time=ensure_utc(model.trigger_time),
            )
            for model, device_type in rows
        ]
        next_cursor = None
        if has_more and mapped:
            last = mapped[-1]
            next_cursor = encode_cursor(f"{last.trigger_time.isoformat()}|{last.alarm_id}")
        return mapped, next_cursor

    async def alarm(self, alarm_id: str) -> AlarmRecord:
        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(AlarmEventModel, DeviceProfileModel.device_type)
                    .join(
                        DeviceProfileModel,
                        DeviceProfileModel.device_id == AlarmEventModel.device_id,
                    )
                    .where(AlarmEventModel.alarm_id == alarm_id)
                )
            ).one_or_none()
        if not row:
            raise ResourceNotFoundError("Alarm not found")
        model, device_type = row
        return AlarmRecord(
            **{
                column.name: getattr(model, column.name)
                for column in AlarmEventModel.__table__.columns
                if column.name != "trigger_time"
            },
            device_type=device_type,
            trigger_time=ensure_utc(model.trigger_time),
        )

    async def sessions(
        self, filters: dict[str, object], limit: int, cursor: str | None
    ) -> tuple[list[DiagnosisSessionItem], str | None]:
        query = select(DiagnosisSessionModel, DiagnosisRunModel).outerjoin(
            DiagnosisRunModel, DiagnosisRunModel.id == DiagnosisSessionModel.run_id
        )
        for name in (
            "phase",
            "source",
            "site_id",
            "device_id",
            "alarm_id",
            "created_by",
            "latest_review_status",
            "risk_level",
        ):
            if filters.get(name):
                query = query.where(getattr(DiagnosisSessionModel, name) == filters[name])
        if filters.get("from_time"):
            query = query.where(
                DiagnosisSessionModel.created_at >= query_datetime(filters["from_time"])
            )
        if filters.get("to_time"):
            query = query.where(
                DiagnosisSessionModel.created_at <= query_datetime(filters["to_time"])
            )
        q = str(filters.get("q") or "").strip()
        if q:
            like = f"%{q}%"
            query = query.where(
                or_(
                    DiagnosisSessionModel.id.like(like),
                    DiagnosisSessionModel.device_id.like(like),
                    DiagnosisSessionModel.alarm_name.like(like),
                    DiagnosisSessionModel.final_summary.like(like),
                )
            )
        after = decode_cursor(cursor)
        if after:
            parts = after.split("|", 1)
            if len(parts) != 2:
                raise InvalidRequestError("Cursor is invalid")
            try:
                at = query_datetime(parts[0])
            except ValueError as exc:
                raise InvalidRequestError("Cursor is invalid") from exc
            query = query.where(
                or_(
                    DiagnosisSessionModel.updated_at < at,
                    and_(
                        DiagnosisSessionModel.updated_at == at,
                        DiagnosisSessionModel.id > parts[1],
                    ),
                )
            )
        query = query.order_by(
            DiagnosisSessionModel.updated_at.desc(), DiagnosisSessionModel.id
        ).limit(limit + 1)
        async with self.session_factory() as session:
            rows = (await session.execute(query)).all()
        has_more = len(rows) > limit
        rows = rows[:limit]
        items = [
            DiagnosisSessionItem(
                session_id=model.id,
                run_id=model.run_id,
                source=model.source,
                site_id=model.site_id,
                device_id=model.device_id,
                alarm_id=model.alarm_id,
                alarm_name=model.alarm_name,
                phase=model.phase,
                risk_level=model.risk_level,
                trace_id=model.trace_id,
                created_by=model.created_by,
                latest_review_status=model.latest_review_status,
                final_summary=model.final_summary,
                diagnosis_template_id=run.diagnosis_template_id if run else None,
                diagnosis_template_version=(run.diagnosis_template_version if run else None),
                alarm_category=run.alarm_category if run else None,
                guardrail_status=run.guardrail_status if run else None,
                failure_category=run.failure_category if run else None,
                created_at=ensure_utc(model.created_at),
                updated_at=ensure_utc(model.updated_at),
            )
            for model, run in rows
        ]
        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = encode_cursor(f"{last.updated_at.isoformat()}|{last.session_id}")
        return items, next_cursor
