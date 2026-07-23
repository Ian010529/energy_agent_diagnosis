import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from sqlalchemy import delete

from energy_agent.app import create_app
from energy_agent.core.config import Settings
from energy_agent.persistence.models import (
    AlarmEventModel,
    DeviceProfileModel,
    DiagnosisAlarmDedupModel,
    DiagnosisResultModel,
    DiagnosisRunModel,
    DiagnosisSessionModel,
    DiagnosisStepLogModel,
    DiagnosisTimelineEventModel,
    MaintenanceTicketModel,
    ManualChunkModel,
)
from energy_agent.persistence.mysql import create_mysql_engine, create_session_factory

MYSQL_DSN = "mysql+aiomysql://energy:energy_dev@localhost:3306/energy_agent"
INFLUX_URL = "http://localhost:8086"
INFLUX_TOKEN = "energy-token"
INFLUX_ORG = "energy"
INFLUX_BUCKET = "energy_metrics"
DEVICE = "PCS-PHASE2-1"
DEVICE_NO_DATA = "PCS-PHASE2-NODATA"
ALARM = "ALARM-PHASE2-1"
ALARM_NO_DATA = "ALARM-PHASE2-NODATA"
ALARM_NAME = "PCS机柜温度持续升高"


async def _seed_mysql() -> None:
    engine = create_mysql_engine(MYSQL_DSN)
    factory = create_session_factory(engine)
    trigger = datetime.now(UTC).replace(tzinfo=None)
    await _clean_mysql()
    async with factory.begin() as session:
        session.add_all(
            [
                DeviceProfileModel(
                    device_id=DEVICE,
                    site_id="SITE-01",
                    device_type="PCS",
                    device_model="SC5000",
                    manufacturer="EnergyCo",
                    location="A区",
                    status="online",
                    rated_power=5000,
                ),
                DeviceProfileModel(
                    device_id=DEVICE_NO_DATA,
                    site_id="SITE-01",
                    device_type="PCS",
                    device_model="SC5000",
                    manufacturer="EnergyCo",
                    location="A区",
                    status="online",
                    rated_power=5000,
                ),
                AlarmEventModel(
                    alarm_id=ALARM,
                    device_id=DEVICE,
                    site_id="SITE-01",
                    alarm_name=ALARM_NAME,
                    alarm_level="high",
                    trigger_time=trigger,
                    status="active",
                    source_system="ems",
                ),
                AlarmEventModel(
                    alarm_id=ALARM_NO_DATA,
                    device_id=DEVICE_NO_DATA,
                    site_id="SITE-01",
                    alarm_name=ALARM_NAME,
                    alarm_level="high",
                    trigger_time=trigger,
                    status="active",
                    source_system="ems",
                ),
                ManualChunkModel(
                    chunk_id="CHUNK-PHASE2-1",
                    doc_id="DOC-PHASE2-1",
                    device_type="PCS",
                    device_model="SC5000",
                    manufacturer="EnergyCo",
                    alarm_name=ALARM_NAME,
                    chapter_title="散热系统维护",
                    page_no=12,
                    section_type="维护步骤",
                    summary_or_content="温度持续升高时检查散热风扇、滤网堵塞和风道。",
                    version="1.0",
                    verified=True,
                    effective=True,
                ),
                MaintenanceTicketModel(
                    ticket_id="TICKET-PHASE2-VERIFIED",
                    site_id="SITE-01",
                    device_id=DEVICE,
                    device_model="SC5000",
                    alarm_name=ALARM_NAME,
                    fault_symptom="机柜温度持续升高，风扇转速为零",
                    root_cause="散热风扇供电故障",
                    action_taken="授权人员断电后更换风扇",
                    is_verified=True,
                    close_time=trigger,
                ),
                MaintenanceTicketModel(
                    ticket_id="TICKET-PHASE2-UNVERIFIED",
                    site_id="SITE-01",
                    device_id=DEVICE,
                    device_model="SC5000",
                    alarm_name=ALARM_NAME,
                    fault_symptom="温度升高",
                    root_cause="未经审核的猜测",
                    action_taken="无",
                    is_verified=False,
                    close_time=trigger,
                ),
            ]
        )
    await engine.dispose()


async def _clean_mysql() -> None:
    engine = create_mysql_engine(MYSQL_DSN)
    factory = create_session_factory(engine)
    async with factory.begin() as session:
        session_ids = (
            await session.execute(
                DiagnosisSessionModel.__table__.select()
                .with_only_columns(DiagnosisSessionModel.id)
                .where(DiagnosisSessionModel.device_id.in_((DEVICE, DEVICE_NO_DATA)))
            )
        ).scalars()
        ids = list(session_ids)
        if ids:
            await session.execute(
                delete(DiagnosisTimelineEventModel).where(
                    DiagnosisTimelineEventModel.session_id.in_(ids)
                )
            )
            await session.execute(
                delete(DiagnosisResultModel).where(DiagnosisResultModel.session_id.in_(ids))
            )
            await session.execute(
                delete(DiagnosisStepLogModel).where(DiagnosisStepLogModel.session_id.in_(ids))
            )
            await session.execute(
                delete(DiagnosisAlarmDedupModel).where(DiagnosisAlarmDedupModel.session_id.in_(ids))
            )
            await session.execute(
                delete(DiagnosisRunModel).where(DiagnosisRunModel.session_id.in_(ids))
            )
            await session.execute(
                delete(DiagnosisSessionModel).where(DiagnosisSessionModel.id.in_(ids))
            )
        await session.execute(
            delete(MaintenanceTicketModel).where(
                MaintenanceTicketModel.ticket_id.in_(
                    ("TICKET-PHASE2-VERIFIED", "TICKET-PHASE2-UNVERIFIED")
                )
            )
        )
        await session.execute(
            delete(ManualChunkModel).where(ManualChunkModel.chunk_id == "CHUNK-PHASE2-1")
        )
        await session.execute(
            delete(AlarmEventModel).where(AlarmEventModel.alarm_id.in_((ALARM, ALARM_NO_DATA)))
        )
        await session.execute(
            delete(DeviceProfileModel).where(
                DeviceProfileModel.device_id.in_((DEVICE, DEVICE_NO_DATA))
            )
        )
    await engine.dispose()


def _seed_influx() -> None:
    now = datetime.now(UTC)
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    points = []
    values = {
        "cabinet_temperature": (40, 48),
        "ambient_temperature": (31, 32),
        "fan_speed": (0, 0),
        "fan_status": (0, 0),
        "output_power": (4200, 4700),
        "dc_current": (800, 850),
    }
    for metric, pair in values.items():
        for offset, value in ((-10, pair[0]), (-1, pair[1])):
            points.append(
                Point("pcs_metrics")
                .tag("device_id", DEVICE)
                .tag("site_id", "SITE-01")
                .tag("device_model", "SC5000")
                .tag("metric_name", metric)
                .field("value", float(value))
                .time(now + timedelta(minutes=offset))
            )
    client.write_api(write_options=SYNCHRONOUS).write(
        bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=points
    )
    client.close()


@pytest.fixture
def phase2_data() -> None:
    asyncio.run(_seed_mysql())
    _seed_influx()
    yield
    asyncio.run(_clean_mysql())
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    client.delete_api().delete(
        datetime(1970, 1, 1, tzinfo=UTC),
        datetime.now(UTC) + timedelta(days=1),
        f'device_id="{DEVICE}"',
        bucket=INFLUX_BUCKET,
        org=INFLUX_ORG,
    )
    client.close()


def _create(
    client: TestClient,
    device_id: str,
    alarm_id: str,
    *,
    source: str = "alarm",
) -> dict[str, object]:
    response = client.post(
        "/api/v1/diagnosis/sessions",
        json={
            "source": source,
            "site_id": "SITE-01",
            "device_id": device_id,
            "alarm_id": alarm_id,
            "alarm_name": ALARM_NAME,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.integration
def test_completed_readback_sse_and_step_logs(phase2_data: None) -> None:
    with TestClient(create_app(Settings(app_env="test"))) as client:
        created = _create(client, DEVICE, ALARM)
        response = client.post(
            "/api/v1/diagnosis/chat",
            headers={"Idempotency-Key": "phase2-completed"},
            json={
                "session_id": created["session_id"],
                "message": "请诊断 PCS 机柜温度持续升高",
                "clarification_answers": [],
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["phase"] == "COMPLETED"
        assert 2 <= len(body["result"]["candidate_causes"]) <= 4
        evidence_ids = {item["evidence_id"] for item in body["result"]["evidence"]}
        assert all(
            set(cause["supporting_evidence"]) <= evidence_ids
            for cause in body["result"]["candidate_causes"]
        )
        assert "ticket:TICKET-PHASE2-UNVERIFIED" not in evidence_ids
        assert "vector_retrieval" not in body["degraded_components"]
        replay = client.post(
            "/api/v1/diagnosis/chat",
            headers={"Idempotency-Key": "phase2-completed"},
            json={
                "session_id": created["session_id"],
                "message": "请诊断 PCS 机柜温度持续升高",
                "clarification_answers": [],
            },
        )
        assert replay.status_code == 200
        assert replay.json()["run_id"] == body["run_id"]
        conflict = client.post(
            "/api/v1/diagnosis/chat",
            headers={"Idempotency-Key": "phase2-completed"},
            json={
                "session_id": created["session_id"],
                "message": "不同请求",
                "clarification_answers": [],
            },
        )
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"

        assert client.portal is not None
        client.portal.call(
            client.app.state.container.providers.redis.delete,
            client.app.state.container.session_store.key(str(created["session_id"])),
        )
        readback = client.get(f"/api/v1/diagnosis/sessions/{created['session_id']}")
        assert readback.status_code == 200
        assert readback.json()["result"]["summary"] == body["result"]["summary"]

        stream_created = _create(client, DEVICE, ALARM, source="chat")
        with client.stream(
            "POST",
            f"/api/v1/diagnosis/sessions/{stream_created['session_id']}/messages/stream",
            json={"message": "诊断温度告警", "clarification_answers": []},
        ) as stream:
            text = "".join(stream.iter_text())
        events = [
            line.removeprefix("event: ") for line in text.splitlines() if line.startswith("event: ")
        ]
        assert events == [
            "intent_identified",
            "data_fetch_started",
            "retrieval_completed",
            "draft_generated",
            "completed",
        ]

    async def assert_logs() -> None:
        engine = create_mysql_engine(MYSQL_DSN)
        factory = create_session_factory(engine)
        async with factory() as session:
            logs = (
                await session.execute(
                    DiagnosisStepLogModel.__table__.select().where(
                        DiagnosisStepLogModel.session_id == created["session_id"]
                    )
                )
            ).all()
        await engine.dispose()
        names = {row.step_name for row in logs}
        assert "agent.intent_router" in names
        assert "agent.memory_writer" in names
        assert "tool.query_timeseries_window" in names
        assert "tool.query_graph_relations" in names
        assert len({name for name in names if name.startswith("tool.")}) == 6

    asyncio.run(assert_logs())


@pytest.mark.integration
def test_need_input_followup_and_influx_degradation(phase2_data: None) -> None:
    with TestClient(create_app(Settings(app_env="test"))) as client:
        created = _create(client, DEVICE_NO_DATA, ALARM_NO_DATA)
        first = client.post(
            "/api/v1/diagnosis/chat",
            json={
                "session_id": created["session_id"],
                "message": "诊断温度告警",
                "clarification_answers": [],
            },
        ).json()
        assert first["phase"] == "NEED_USER_INPUT"
        assert first["clarification_questions"]
        followup = client.post(
            f"/api/v1/diagnosis/sessions/{created['session_id']}/messages",
            json={
                "message": "现场检查结果",
                "clarification_answers": [
                    {
                        "question_id": first["clarification_questions"][0]["question_id"],
                        "answer": "现场确认风扇不转，滤网有明显积尘",
                    }
                ],
            },
        ).json()
        assert followup["run_id"] != first["run_id"]
        assert followup["phase"] == "COMPLETED"

    settings = Settings(app_env="test", influxdb_url="http://127.0.0.1:1")
    with TestClient(create_app(settings)) as client:
        created = _create(client, DEVICE, ALARM)
        degraded = client.post(
            "/api/v1/diagnosis/chat",
            json={
                "session_id": created["session_id"],
                "message": "诊断温度告警",
                "clarification_answers": [],
            },
        ).json()
        assert degraded["phase"] == "NEED_USER_INPUT"
        assert "influxdb" in degraded["degraded_components"]
