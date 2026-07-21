import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from sqlalchemy import delete

from energy_agent.agent.templates.definitions import TEMPLATES
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

pytestmark = pytest.mark.integration

MYSQL_DSN = "mysql+aiomysql://energy:energy_dev@localhost:3306/energy_agent"
INFLUX_URL = "http://localhost:8086"
INFLUX_TOKEN = "energy-token"
INFLUX_ORG = "energy"
INFLUX_BUCKET = "energy_metrics"


async def _seed_mysql() -> None:
    engine = create_mysql_engine(MYSQL_DSN)
    factory = create_session_factory(engine)
    trigger = datetime.now(UTC).replace(tzinfo=None)
    async with factory.begin() as session:
        for index, template in enumerate(TEMPLATES):
            device_id = f"PHASE5-DEVICE-{index}"
            alarm_id = f"PHASE5-ALARM-{index}"
            alarm_name = template.alarm_patterns[0]
            terms = " ".join(template.candidate_rules[0].evidence_terms)
            session.add_all(
                [
                    DeviceProfileModel(
                        device_id=device_id,
                        site_id="SITE-PHASE5",
                        device_type=template.device_type,
                        device_model=f"MODEL-{index}",
                        manufacturer="EnergyCo",
                        location="A区",
                        status="online",
                        rated_power=5000,
                    ),
                    AlarmEventModel(
                        alarm_id=alarm_id,
                        device_id=device_id,
                        site_id="SITE-PHASE5",
                        alarm_name=alarm_name,
                        alarm_level="high",
                        trigger_time=trigger,
                        status="active",
                        source_system="ems",
                    ),
                    ManualChunkModel(
                        chunk_id=f"PHASE5-CHUNK-{index}",
                        doc_id=f"PHASE5-DOC-{index}",
                        device_type=template.device_type,
                        device_model=f"MODEL-{index}",
                        manufacturer="EnergyCo",
                        alarm_name=alarm_name,
                        chapter_title="排查步骤",
                        page_no=1,
                        section_type="维护步骤",
                        summary_or_content=f"{terms}，候选方向 {template.candidate_rules[0].cause}",
                        version="1.0",
                        verified=True,
                        effective=True,
                    ),
                    MaintenanceTicketModel(
                        ticket_id=f"PHASE5-TICKET-{index}",
                        site_id="SITE-PHASE5",
                        device_id=device_id,
                        device_model=f"MODEL-{index}",
                        alarm_name=alarm_name,
                        fault_symptom=terms,
                        root_cause=template.candidate_rules[0].cause,
                        action_taken=template.inspection_steps[0],
                        is_verified=True,
                        close_time=trigger,
                    ),
                ]
            )
    await engine.dispose()


async def _clean_mysql() -> None:
    engine = create_mysql_engine(MYSQL_DSN)
    factory = create_session_factory(engine)
    async with factory.begin() as session:
        device_ids = [f"PHASE5-DEVICE-{index}" for index in range(len(TEMPLATES))]
        session_ids = list(
            (
                await session.execute(
                    DiagnosisSessionModel.__table__.select()
                    .with_only_columns(DiagnosisSessionModel.id)
                    .where(DiagnosisSessionModel.device_id.in_(device_ids))
                )
            ).scalars()
        )
        if session_ids:
            await session.execute(
                delete(DiagnosisTimelineEventModel).where(
                    DiagnosisTimelineEventModel.session_id.in_(session_ids)
                )
            )
            await session.execute(
                delete(DiagnosisResultModel).where(DiagnosisResultModel.session_id.in_(session_ids))
            )
            await session.execute(
                delete(DiagnosisStepLogModel).where(
                    DiagnosisStepLogModel.session_id.in_(session_ids)
                )
            )
            await session.execute(
                delete(DiagnosisAlarmDedupModel).where(
                    DiagnosisAlarmDedupModel.session_id.in_(session_ids)
                )
            )
            await session.execute(
                delete(DiagnosisRunModel).where(DiagnosisRunModel.session_id.in_(session_ids))
            )
            await session.execute(
                delete(DiagnosisSessionModel).where(DiagnosisSessionModel.id.in_(session_ids))
            )
        await session.execute(
            delete(MaintenanceTicketModel).where(
                MaintenanceTicketModel.ticket_id.like("PHASE5-TICKET-%")
            )
        )
        await session.execute(
            delete(ManualChunkModel).where(ManualChunkModel.chunk_id.like("PHASE5-CHUNK-%"))
        )
        await session.execute(
            delete(AlarmEventModel).where(AlarmEventModel.alarm_id.like("PHASE5-ALARM-%"))
        )
        await session.execute(
            delete(DeviceProfileModel).where(DeviceProfileModel.device_id.like("PHASE5-DEVICE-%"))
        )
    await engine.dispose()


def _seed_influx() -> None:
    now = datetime.now(UTC)
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    points: list[Point] = []
    for index, template in enumerate(TEMPLATES):
        for metric in template.metrics:
            for offset, value in ((-10, 1.0), (-1, 2.0)):
                points.append(
                    Point(template.measurements[0])
                    .tag("device_id", f"PHASE5-DEVICE-{index}")
                    .tag("site_id", "SITE-PHASE5")
                    .tag("device_model", f"MODEL-{index}")
                    .tag("metric_name", metric)
                    .field("value", value)
                    .time(now + timedelta(minutes=offset))
                )
    client.write_api(write_options=SYNCHRONOUS).write(
        bucket=INFLUX_BUCKET,
        org=INFLUX_ORG,
        record=points,
    )
    client.close()


@pytest.fixture
def phase5_scenario_data() -> None:
    asyncio.run(_clean_mysql())
    asyncio.run(_seed_mysql())
    _seed_influx()
    yield
    asyncio.run(_clean_mysql())
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    client.delete_api().delete(
        datetime(1970, 1, 1, tzinfo=UTC),
        datetime.now(UTC) + timedelta(days=1),
        'site_id="SITE-PHASE5"',
        bucket=INFLUX_BUCKET,
        org=INFLUX_ORG,
    )
    client.close()


def test_five_templates_complete_through_shared_langgraph(
    phase5_scenario_data: None,
) -> None:
    settings = Settings(app_env="test", graph_mode="disabled")
    with TestClient(create_app(settings)) as client:
        for index, template in enumerate(TEMPLATES):
            created = client.post(
                "/api/v1/diagnosis/sessions",
                json={
                    "source": "alarm",
                    "site_id": "SITE-PHASE5",
                    "device_id": f"PHASE5-DEVICE-{index}",
                    "alarm_id": f"PHASE5-ALARM-{index}",
                    "alarm_name": template.alarm_patterns[0],
                },
            )
            assert created.status_code == 201, created.text
            response = client.post(
                "/api/v1/diagnosis/chat",
                json={
                    "session_id": created.json()["session_id"],
                    "message": f"请诊断 {template.alarm_patterns[0]}",
                    "clarification_answers": [],
                },
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["phase"] == "COMPLETED", (template.template_id, body)
            assert body["result"]["candidate_causes"]
            assert len(body["tool_summaries"]) <= 8
