from datetime import UTC, datetime

from sqlalchemy.dialects.mysql import insert

from energy_agent.evaluation.contracts import RuntimeSample
from energy_agent.persistence.models import AlarmEventModel
from energy_agent.persistence.mysql import create_mysql_engine, create_session_factory


def mysql_utc_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(UTC).replace(tzinfo=None)


async def materialize_runtime_alarms(mysql_dsn: str, samples: list[RuntimeSample]) -> int:
    """Materialize runtime inputs only; this function never receives or persists Gold."""
    engine = create_mysql_engine(mysql_dsn)
    factory = create_session_factory(engine)
    rows = [
        {
            "alarm_id": sample.alarm_id,
            "device_id": sample.device_id,
            "site_id": sample.site_id,
            "alarm_name": sample.alarm_name,
            "alarm_level": "warning",
            "trigger_time": mysql_utc_datetime(sample.trigger_time),
            "status": "ACTIVE",
            "source_system": "synthetic_evaluation_runtime",
        }
        for sample in samples
        if sample.trigger_time
    ]
    try:
        async with factory.begin() as session:
            for row in rows:
                statement = insert(AlarmEventModel).values(**row)
                statement = statement.on_duplicate_key_update(
                    device_id=statement.inserted.device_id,
                    site_id=statement.inserted.site_id,
                    alarm_name=statement.inserted.alarm_name,
                    alarm_level=statement.inserted.alarm_level,
                    trigger_time=statement.inserted.trigger_time,
                    status=statement.inserted.status,
                    source_system=statement.inserted.source_system,
                )
                await session.execute(statement)
    finally:
        await engine.dispose()
    return len(rows)
