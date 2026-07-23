import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from energy_agent.agent.service import DiagnosisService
from energy_agent.agent.state import Evidence
from energy_agent.agent.templates.routing import DEFAULT_TEMPLATE_REGISTRY
from energy_agent.agent.workflow import _extract_entity_ids
from energy_agent.api.auth import require_roles
from energy_agent.api.evidence import READ_ROLES
from energy_agent.catalog.repository import decode_cursor, encode_cursor, query_datetime
from energy_agent.catalog.service import CatalogService, alarm_support
from energy_agent.contracts.common import DiagnosisPhase, SessionSource
from energy_agent.contracts.diagnosis import (
    CreateSessionRequest,
    DiagnosisChatRequest,
    SessionMemoryPayload,
)
from energy_agent.core.context import ActorContext, ActorRole
from energy_agent.core.errors import (
    InvalidRequestError,
    PermissionDeniedError,
    ResourceNotFoundError,
)
from energy_agent.evidence.service import EvidenceService
from energy_agent.observability.tracing import LocalTracer
from energy_agent.timeline.contracts import TimelineEventType, timeline_event_id
from energy_agent.tools.registry import ToolRegistry


def evidence_service(**overrides: object) -> EvidenceService:
    dependencies = {
        "sessions": SimpleNamespace(get=AsyncMock()),
        "results": SimpleNamespace(latest=AsyncMock(return_value=None)),
        "runs": SimpleNamespace(latest=AsyncMock(return_value=None)),
        "memory": SimpleNamespace(get=AsyncMock(return_value=None)),
        "sources": SimpleNamespace(
            manual=AsyncMock(return_value=None),
            ticket=AsyncMock(return_value=None),
            case=AsyncMock(return_value=None),
        ),
        "catalog": SimpleNamespace(alarm=AsyncMock()),
        "timeseries": SimpleNamespace(query_points=AsyncMock(return_value={})),
    }
    dependencies.update(overrides)
    return EvidenceService(**dependencies)  # type: ignore[arg-type]


def test_catalog_cursor_is_opaque_and_round_trips() -> None:
    raw = "2026-07-21T08:30:00+00:00|device-001"
    encoded = encode_cursor(raw)
    assert raw not in encoded
    assert decode_cursor(encoded) == raw


def test_invalid_catalog_cursor_is_rejected() -> None:
    with pytest.raises(InvalidRequestError, match="Cursor is invalid"):
        decode_cursor("%%%")


def test_entity_parser_extracts_traceable_device_and_alarm_ids() -> None:
    text = (
        "设备 pilot_medium_v1-SITE-PILOT-01-PCS-0001，"
        "告警 ALARM-pilot_medium_v1-29127340057e08cdc97e"
    )
    assert _extract_entity_ids(text) == (
        "pilot_medium_v1-SITE-PILOT-01-PCS-0001",
        "ALARM-pilot_medium_v1-29127340057e08cdc97e",
    )
    assert _extract_entity_ids("只有 PCS 温度升高现象") == (None, None)


def test_query_datetime_normalizes_offsets_for_mysql() -> None:
    value = query_datetime("2026-07-21T12:00:00+04:00")
    assert value.isoformat() == "2026-07-21T08:00:00"
    assert value.tzinfo is None
    assert query_datetime("2026-07-21T08:00:00").replace(tzinfo=UTC).tzinfo == UTC


def test_alarm_support_reuses_template_routing() -> None:
    category, template_id, version = alarm_support("PCS", "PCS 机柜温度异常")
    assert category
    assert template_id
    assert version
    assert alarm_support("UNKNOWN", "unmapped alarm") == (None, None, None)
    assert len(DEFAULT_TEMPLATE_REGISTRY.templates) == 5


def test_timeline_event_id_is_idempotent_and_key_sensitive() -> None:
    first = timeline_event_id("s1", TimelineEventType.USER_MESSAGE, "run-1")
    assert first == timeline_event_id("s1", TimelineEventType.USER_MESSAGE, "run-1")
    assert first != timeline_event_id("s1", TimelineEventType.USER_MESSAGE, "run-2")
    assert len(first) == 64


def test_timeline_persists_only_business_events() -> None:
    assert {item.value for item in TimelineEventType} == {
        "user_message",
        "clarification_question",
        "clarification_answer",
        "diagnosis_result",
        "review_submitted",
        "case_created",
    }


@pytest.mark.asyncio
async def test_evidence_detail_rejects_cross_session_reference() -> None:
    service = evidence_service(
        sessions=SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(trace_id="trace-1"))),
        results=SimpleNamespace(latest=AsyncMock(return_value=SimpleNamespace(evidence=[]))),
    )
    with pytest.raises(ResourceNotFoundError, match="does not belong"):
        await service.detail("session-1", "evidence-from-another-session")


@pytest.mark.asyncio
async def test_evidence_detail_reads_in_progress_session_memory() -> None:
    evidence = Evidence(
        evidence_id="graph:relation-1",
        source_type="graph",
        source_id="relation-1",
        summary="风扇与机柜温升相关",
        citation="[图谱: relation-1]",
        verified=True,
        reliability=0.8,
        relevance=0.9,
    )

    service = evidence_service(
        sessions=SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(trace_id="trace-1"))),
        memory=SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(evidence=[evidence]))),
    )
    detail = await service.detail("session-1", evidence.evidence_id)

    assert detail.evidence_id == evidence.evidence_id
    assert detail.content_excerpt == evidence.summary


@pytest.mark.asyncio
async def test_timeseries_metric_must_belong_to_run_template() -> None:
    session = SimpleNamespace(device_id="PCS-001", trace_id="trace-1")
    run = SimpleNamespace(diagnosis_template_id="pcs_temperature_abnormal_v1")
    service = evidence_service(
        sessions=SimpleNamespace(get=AsyncMock(return_value=session)),
        runs=SimpleNamespace(latest=AsyncMock(return_value=run)),
    )
    with pytest.raises(InvalidRequestError, match="metric is not allowed"):
        await service.timeseries("session-1", None, "admin_only_metric", None, None)


@pytest.mark.asyncio
async def test_timeseries_recovers_window_from_persisted_alarm() -> None:
    trigger = datetime(2026, 5, 29, 9, 8, tzinfo=UTC)
    session = SimpleNamespace(device_id="PCS-001", alarm_id="ALARM-001", trace_id="trace-1")
    run = SimpleNamespace(diagnosis_template_id="pcs_temperature_abnormal_v1")
    query_points = AsyncMock(
        return_value={
            metric: []
            for metric in DEFAULT_TEMPLATE_REGISTRY.get("pcs_temperature_abnormal_v1").metrics
        }
    )
    service = evidence_service(
        sessions=SimpleNamespace(get=AsyncMock(return_value=session)),
        runs=SimpleNamespace(latest=AsyncMock(return_value=run)),
        catalog=SimpleNamespace(
            alarm=AsyncMock(return_value=SimpleNamespace(trigger_time=trigger))
        ),
        timeseries=SimpleNamespace(query_points=query_points),
    )
    response = await service.timeseries("session-1", None, None, None, None)

    assert response.window_source == "alarm"
    assert response.end_time == trigger
    assert response.start_time == trigger - timedelta(minutes=30)
    assert response.empty_reason is not None
    assert query_points.await_args.args[2:4] == (
        response.start_time.isoformat(),
        response.end_time.isoformat(),
    )


def diagnosis_service() -> tuple[DiagnosisService, SimpleNamespace]:
    dependencies = SimpleNamespace(
        sessions=SimpleNamespace(create=AsyncMock(), get=AsyncMock(), update=AsyncMock()),
        runs=SimpleNamespace(
            create=AsyncMock(),
            find_idempotent=AsyncMock(return_value=None),
            finish=AsyncMock(),
            set_hardening_outcome=AsyncMock(),
        ),
        results=SimpleNamespace(),
        step_logs=SimpleNamespace(create=AsyncMock()),
        memory=SimpleNamespace(save=AsyncMock(), get=AsyncMock(return_value=None)),
    )
    service = DiagnosisService(
        sessions=dependencies.sessions,
        runs=dependencies.runs,
        results=dependencies.results,
        step_logs=dependencies.step_logs,
        memory=dependencies.memory,
        tools=ToolRegistry(),
        tracer=LocalTracer(),
    )
    return service, dependencies


@pytest.mark.asyncio
async def test_create_session_initial_run_is_not_marked_running() -> None:
    service, dependencies = diagnosis_service()
    await service.create_session(CreateSessionRequest(source=SessionSource.CHAT), None)

    run = dependencies.runs.create.await_args.args[0]
    assert run.status == "initialized"
    assert run.run_type == "session_init"


@pytest.mark.asyncio
async def test_cancelled_stream_persists_terminal_session(monkeypatch) -> None:
    service, dependencies = diagnosis_service()
    persisted = SessionMemoryPayload(
        session_id="session-1",
        phase=DiagnosisPhase.INIT,
        run_id="init-run",
        trace_id="trace-1",
        updated_at=datetime.now(UTC),
    )
    dependencies.memory.get.side_effect = [persisted, persisted]
    dependencies.sessions.get.return_value = SimpleNamespace(
        id="session-1",
        source=SessionSource.CHAT,
        site_id=None,
        device_id=None,
        alarm_id=None,
        alarm_name=None,
        phase=DiagnosisPhase.INIT,
        run_id="init-run",
        trace_id="trace-1",
    )
    graph = SimpleNamespace(ainvoke=AsyncMock(side_effect=asyncio.CancelledError))
    monkeypatch.setattr(
        "energy_agent.agent.runtime_factory.build_diagnosis_graph", lambda *args, **kwargs: graph
    )

    with pytest.raises(asyncio.CancelledError):
        await service.diagnose(DiagnosisChatRequest(session_id="session-1", message="diagnose"))

    run_id = dependencies.runs.create.await_args.args[0].id
    dependencies.runs.finish.assert_awaited_once_with(run_id, DiagnosisPhase.FAILED, "cancelled")
    assert dependencies.sessions.update.await_args_list[-1].args[1].phase == DiagnosisPhase.FAILED
    assert (
        dependencies.runs.set_hardening_outcome.await_args.kwargs["failure_category"]
        == "stream_disconnected"
    )
    assert dependencies.memory.save.await_args.args[0].phase == DiagnosisPhase.FAILED


@pytest.mark.asyncio
async def test_catalog_service_preserves_cursor_pagination_signal() -> None:
    repository = SimpleNamespace(devices=AsyncMock(return_value=([], "opaque-next")))
    service = CatalogService(repository, SimpleNamespace())
    page = await service.devices({}, 20, None)
    assert page.next_cursor == "opaque-next"
    assert page.has_more is True


def test_viewer_is_read_only_for_phase7_resources() -> None:
    viewer = ActorContext("viewer-1", ActorRole.VIEWER, "development_headers")
    require_roles(viewer, READ_ROLES)
    with pytest.raises(PermissionDeniedError):
        require_roles(viewer, {ActorRole.OPERATOR, ActorRole.REVIEWER, ActorRole.ADMIN})
