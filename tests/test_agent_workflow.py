"""验证阶段 4 LangGraph Agent 主链路。"""

import pytest

from energy_agent_diagnosis.agent import DiagnosisAgentService
from energy_agent_diagnosis.contracts import (
    DiagnosisMessageCreate,
    DiagnosisSessionCreate,
    DiagnosisStatus,
    Role,
)
from energy_agent_diagnosis.core.config import ProviderSettings, RetrievalSettings, Settings
from energy_agent_diagnosis.memory import InMemoryDiagnosisSessionStore
from energy_agent_diagnosis.providers import build_provider_registry


def build_service(settings: Settings | None = None) -> DiagnosisAgentService:
    resolved = settings or Settings()
    return DiagnosisAgentService(
        registry=build_provider_registry(ProviderSettings()),
        settings=resolved,
        store=InMemoryDiagnosisSessionStore(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("alarm_id", "message", "expected_cause_term"),
    [
        ("ALARM-20260626-0001", "PCS机柜温度持续升高，先查什么？", "散热"),
        ("ALARM-20260626-0003", "逆变器通讯中断，如何排查？", "通讯"),
        ("ALARM-20260626-0006", "齿轮箱温度偏高，冷却回路是否异常？", "散热"),
    ],
)
async def test_three_typical_alarms_complete_agent_workflow(
    alarm_id: str,
    message: str,
    expected_cause_term: str,
) -> None:
    service = build_service()

    snapshot = await service.chat(
        DiagnosisSessionCreate(alarm_id=alarm_id, message=message),
        trace_id=f"trace-{alarm_id}",
        user_id="operator-1",
        role=Role.OPERATOR,
    )

    assert snapshot.status is DiagnosisStatus.COMPLETED
    assert snapshot.result and snapshot.result.status is DiagnosisStatus.COMPLETED
    assert snapshot.evidence_package and snapshot.evidence_package.ranked_evidence
    assert snapshot.tool_calls
    assert {call.tool_name for call in snapshot.tool_calls}.issuperset(
        {"get_alarm_detail", "get_device_profile", "query_timeseries_window"}
    )
    cause = snapshot.result.candidate_causes[0]
    assert expected_cause_term in cause.cause
    evidence_ids = {item.evidence_id for item in snapshot.evidence_package.ranked_evidence}
    assert set(cause.supporting_evidence).issubset(evidence_ids)
    assert snapshot.events[-1].event == "diagnosis_completed"


@pytest.mark.asyncio
async def test_agent_pauses_for_user_input_and_resumes_after_clarification() -> None:
    service = build_service(
        Settings(retrieval=RetrievalSettings(score_threshold=1.0, min_strong_evidence_count=10))
    )
    created = await service.create_session(
        DiagnosisSessionCreate(
            session_id="diag-needs-input",
            alarm_id="ALARM-20260626-0001",
            message="PCS机柜温度持续升高",
        ),
        trace_id="trace-need-input",
        user_id="operator-1",
        role=Role.OPERATOR,
    )

    paused = await service.send_message(
        created.session_id,
        DiagnosisMessageCreate(message="PCS机柜温度持续升高"),
        trace_id="trace-need-input",
    )

    assert paused.status is DiagnosisStatus.NEED_USER_INPUT
    assert paused.result and paused.result.clarification_questions

    resumed = await service.send_message(
        created.session_id,
        DiagnosisMessageCreate(message="现场确认风扇有异响，柜内温度仍在升高"),
        trace_id="trace-need-input",
    )

    assert resumed.status is DiagnosisStatus.COMPLETED
    assert resumed.result and resumed.result.candidate_causes
    assert any(event.event == "need_user_input" for event in resumed.events)
