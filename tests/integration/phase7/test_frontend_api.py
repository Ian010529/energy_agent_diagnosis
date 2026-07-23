import asyncio
import os
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from sqlalchemy import delete

from energy_agent.app import create_app
from energy_agent.catalog.repository import CatalogRepository
from energy_agent.catalog.service import CatalogService
from energy_agent.contracts.common import SessionSource
from energy_agent.contracts.diagnosis import DiagnosisRunCreate, DiagnosisSessionCreate
from energy_agent.core.config import Settings
from energy_agent.core.ids import new_id
from energy_agent.observability.tracing import LocalTracer
from energy_agent.persistence.models import (
    AlarmEventModel,
    DeviceProfileModel,
    DiagnosisRunModel,
    DiagnosisSessionModel,
    DiagnosisTimelineEventModel,
)
from energy_agent.persistence.mysql import create_mysql_engine, create_session_factory
from energy_agent.persistence.repositories.cases import CaseRepository
from energy_agent.persistence.repositories.diagnosis_run import DiagnosisRunRepository
from energy_agent.persistence.repositories.diagnosis_session import (
    DiagnosisSessionRepository,
)
from energy_agent.providers.influxdb import InfluxTimeseriesProvider
from energy_agent.timeline.contracts import (
    TimelineEventCreate,
    TimelineEventType,
    timeline_event_id,
)
from energy_agent.timeline.repository import TimelineRepository

pytestmark = pytest.mark.integration
MYSQL_DSN = os.getenv(
    "TEST_MYSQL_DSN", "mysql+aiomysql://energy:energy_dev@localhost:3306/energy_agent"
)


@pytest_asyncio.fixture
async def mysql_factory():
    engine = create_mysql_engine(MYSQL_DSN)
    factory = create_session_factory(engine)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_catalog_real_mysql_filters_and_template_derivation(
    mysql_factory,
) -> None:
    suffix = new_id()[:8]
    device_id, alarm_id = f"PCS-P7-{suffix}", f"ALARM-P7-{suffix}"
    async with mysql_factory.begin() as session:
        session.add(
            DeviceProfileModel(
                device_id=device_id,
                site_id="SITE-PHASE7",
                device_type="PCS",
                device_model="SC5000",
                manufacturer="EnergyCo",
                status="online",
            )
        )
        session.add(
            AlarmEventModel(
                alarm_id=alarm_id,
                device_id=device_id,
                site_id="SITE-PHASE7",
                alarm_name="PCS 机柜温度异常",
                alarm_level="high",
                trigger_time=datetime.now(UTC).replace(tzinfo=None),
                status="active",
                source_system="phase7-test",
            )
        )
    try:
        repository = CatalogRepository(mysql_factory)
        devices, _ = await repository.devices({"site_id": "SITE-PHASE7"}, 50, None)
        alarms = await CatalogService(repository, Settings(app_env="test")).alarms(
            {"device_id": device_id, "supported": True}, 50, None
        )
        assert any(item.device_id == device_id for item in devices)
        assert len(alarms.items) == 1
        assert alarms.items[0].template_id == "pcs_temperature_abnormal_v1"
    finally:
        async with mysql_factory.begin() as session:
            await session.execute(
                delete(AlarmEventModel).where(AlarmEventModel.alarm_id == alarm_id)
            )
            await session.execute(
                delete(DeviceProfileModel).where(DeviceProfileModel.device_id == device_id)
            )


@pytest.mark.asyncio
async def test_catalog_alarm_cursor_does_not_skip_unreturned_batch_rows(mysql_factory) -> None:
    suffix = new_id()[:8]
    device_id = f"PCS-P7-PAGE-{suffix}"
    alarm_ids = [f"ALARM-P7-PAGE-{suffix}-{index:02d}" for index in range(25)]
    started_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=1)
    async with mysql_factory.begin() as session:
        session.add(
            DeviceProfileModel(
                device_id=device_id,
                site_id="SITE-PHASE7",
                device_type="PCS",
                device_model="SC5000",
                manufacturer="EnergyCo",
                status="online",
            )
        )
        session.add_all(
            [
                AlarmEventModel(
                    alarm_id=alarm_id,
                    device_id=device_id,
                    site_id="SITE-PHASE7",
                    alarm_name="PCS 机柜温度异常",
                    alarm_level="high",
                    trigger_time=started_at + timedelta(seconds=index),
                    status="active",
                    source_system="phase7-pagination-test",
                )
                for index, alarm_id in enumerate(alarm_ids)
            ]
        )
    try:
        service = CatalogService(CatalogRepository(mysql_factory), Settings(app_env="test"))
        cursor = None
        seen: list[str] = []
        while True:
            page = await service.alarms({"device_id": device_id}, 10, cursor)
            seen.extend(item.alarm_id for item in page.items)
            if not page.next_cursor:
                break
            cursor = page.next_cursor
        assert seen == list(reversed(alarm_ids))
        assert len(seen) == len(set(seen)) == 25
    finally:
        async with mysql_factory.begin() as session:
            await session.execute(
                delete(AlarmEventModel).where(AlarmEventModel.device_id == device_id)
            )
            await session.execute(
                delete(DeviceProfileModel).where(DeviceProfileModel.device_id == device_id)
            )


@pytest.mark.asyncio
async def test_timeline_real_mysql_atomic_sequence_and_idempotent_append(
    mysql_factory,
) -> None:
    session_id, initial_run, message_run, trace_id = (new_id() for _ in range(4))
    sessions = DiagnosisSessionRepository(mysql_factory, LocalTracer())
    runs = DiagnosisRunRepository(mysql_factory, LocalTracer())
    timeline = TimelineRepository(mysql_factory)
    await sessions.create(
        DiagnosisSessionCreate(
            id=session_id,
            source=SessionSource.CHAT,
            trace_id=trace_id,
            run_id=initial_run,
        )
    )
    event = TimelineEventCreate(
        event_id=timeline_event_id(session_id, "user_message", message_run),
        session_id=session_id,
        run_id=message_run,
        event_type=TimelineEventType.USER_MESSAGE,
        actor_id="operator-phase7",
        actor_role="operator",
        payload={"message": "真实 MySQL 时间线"},
    )
    try:
        await runs.create(
            DiagnosisRunCreate(
                id=message_run,
                session_id=session_id,
                trace_id=trace_id,
                request_hash="a" * 64,
            ),
            timeline_event=event,
        )
        first = (await timeline.list(session_id))[0]
        replays = await asyncio.gather(*(timeline.append(event) for _ in range(12)))
        assert first.sequence == 1
        assert {replay.event_id for replay in replays} == {first.event_id}
        assert len(await timeline.list(session_id)) == 1
    finally:
        async with mysql_factory.begin() as session:
            await session.execute(
                delete(DiagnosisTimelineEventModel).where(
                    DiagnosisTimelineEventModel.session_id == session_id
                )
            )
            await session.execute(
                delete(DiagnosisRunModel).where(DiagnosisRunModel.session_id == session_id)
            )
            await session.execute(
                delete(DiagnosisSessionModel).where(DiagnosisSessionModel.id == session_id)
            )


def test_evidence_contract_uses_session_scoped_path() -> None:
    paths = create_app().openapi()["paths"]
    assert "get" in paths["/api/v1/diagnosis/sessions/{session_id}/evidence/{evidence_id}"]
    assert "get" in paths["/api/v1/diagnosis/sessions/{session_id}/timeseries"]


@pytest.mark.asyncio
async def test_evidence_timeseries_real_influx_downsampling() -> None:
    url = os.getenv("TEST_INFLUXDB_URL", "http://localhost:8086")
    token = os.getenv("TEST_INFLUXDB_TOKEN", "energy-token")
    org = os.getenv("TEST_INFLUXDB_ORG", "energy")
    bucket = os.getenv("TEST_INFLUXDB_BUCKET", "energy_metrics")
    device_id = f"PCS-P7-{new_id()[:8]}"
    start = datetime.now(UTC) - timedelta(minutes=3)
    end = datetime.now(UTC) + timedelta(seconds=1)
    client = InfluxDBClient(url=url, token=token, org=org)
    records = [
        Point("pcs_metrics")
        .tag("device_id", device_id)
        .tag("metric_name", "cabinet_temperature")
        .tag("quality", "good")
        .field("value", 40.0 + index / 10)
        .time(start + timedelta(seconds=index))
        for index in range(120)
    ]
    try:
        client.write_api(write_options=SYNCHRONOUS).write(bucket=bucket, org=org, record=records)
        provider = InfluxTimeseriesProvider(client, org, bucket, 5)
        result = await provider.query_points(
            device_id,
            ["cabinet_temperature"],
            start.isoformat(),
            end.isoformat(),
            20,
            measurements=["pcs_metrics"],
        )
        assert 1 <= len(result["cabinet_temperature"]) <= 20
        assert all(point[2] == "good" for point in result["cabinet_temperature"])
    finally:
        client.delete_api().delete(
            start=start - timedelta(seconds=1),
            stop=end + timedelta(seconds=1),
            predicate=f'device_id="{device_id}"',
            bucket=bucket,
            org=org,
        )
        client.close()


@pytest.mark.asyncio
async def test_case_cursor_pagination_uses_real_mysql(mysql_factory) -> None:
    repository = CaseRepository(mysql_factory)
    first, total, cursor = await repository.list_page(
        {}, limit=2, cursor=None, sort="updated_at_desc"
    )
    assert total >= len(first)
    if total > 2:
        assert cursor is not None
        second, second_total, _ = await repository.list_page(
            {}, limit=2, cursor=cursor, sort="updated_at_desc"
        )
        assert second_total == total
        assert {item.case_id for item in first}.isdisjoint(item.case_id for item in second)


def test_phase7_read_authorization_and_viewer_write_denial() -> None:
    settings = Settings(
        app_env="test",
        auth_mode="trusted_headers",
        internal_api_key="phase7-contract-key",
    )
    with TestClient(create_app(settings)) as client:
        unauthenticated = client.get("/api/v1/diagnosis/sessions/missing/evidence/missing")
        assert unauthenticated.status_code == 401

        viewer_headers = {
            "X-Internal-API-Key": "phase7-contract-key",
            "X-Actor-ID": "viewer-phase7",
            "X-Actor-Role": "viewer",
        }
        allowed_read = client.get(
            "/api/v1/diagnosis/sessions/missing/evidence/missing",
            headers=viewer_headers,
        )
        assert allowed_read.status_code == 404
        forbidden_write = client.post(
            "/api/v1/diagnosis/sessions",
            headers=viewer_headers,
            json={"source": "chat"},
        )
        assert forbidden_write.status_code == 403
