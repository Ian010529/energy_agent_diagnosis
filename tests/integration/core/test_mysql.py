from datetime import UTC, datetime

import pytest
from sqlalchemy import delete

from energy_agent.contracts.common import DiagnosisPhase, RiskLevel, SessionSource
from energy_agent.contracts.diagnosis import (
    DiagnosisSessionCreate,
    DiagnosisSessionUpdate,
    StepLogCreate,
)
from energy_agent.core.errors import ResourceNotFoundError
from energy_agent.core.ids import new_id
from energy_agent.observability.tracing import LocalTracer
from energy_agent.persistence.models import DiagnosisSessionModel, DiagnosisStepLogModel
from energy_agent.persistence.repositories.diagnosis_session import (
    DiagnosisSessionRepository,
)
from energy_agent.persistence.repositories.diagnosis_step_log import (
    DiagnosisStepLogRepository,
)

pytestmark = pytest.mark.integration


async def test_mysql_session_and_step_log_readback(mysql_resources) -> None:
    _, factory = mysql_resources
    tracer = LocalTracer()
    sessions = DiagnosisSessionRepository(factory, tracer)
    steps = DiagnosisStepLogRepository(factory, tracer)
    trace_id, run_id, session_id = new_id(), new_id(), new_id()
    try:
        created = await sessions.create(
            DiagnosisSessionCreate(
                id=session_id,
                source=SessionSource.ALARM,
                device_id="PCS-01",
                phase=DiagnosisPhase.INIT,
                trace_id=trace_id,
                run_id=run_id,
            )
        )
        loaded = await sessions.get(session_id, trace_id=trace_id)
        updated = await sessions.update(
            session_id,
            DiagnosisSessionUpdate(phase=DiagnosisPhase.PLAN_READY, risk_level=RiskLevel.LOW),
            trace_id=trace_id,
        )
        step = await steps.create(
            StepLogCreate(
                session_id=session_id,
                run_id=run_id,
                trace_id=trace_id,
                step_name="foundation_node",
                step_status="completed",
                input_snapshot={
                    "password": "must-not-persist",
                    "user_message": "private",
                    "large": "x" * 20_000,
                },
                output_snapshot={"ok": True},
                started_at=datetime.now(UTC),
            )
        )
        logs = await steps.list_by_session(session_id, trace_id=trace_id)
        assert loaded == created
        assert updated.phase == DiagnosisPhase.PLAN_READY
        assert created.created_at.tzinfo == UTC
        assert logs == [step]
        snapshot_text = repr(step.input_snapshot)
        assert "must-not-persist" not in snapshot_text
        assert "private" not in snapshot_text
        assert step.input_snapshot["truncated"] is True
    finally:
        async with factory.begin() as session:
            await session.execute(
                delete(DiagnosisStepLogModel).where(DiagnosisStepLogModel.session_id == session_id)
            )
            await session.execute(
                delete(DiagnosisSessionModel).where(DiagnosisSessionModel.id == session_id)
            )


async def test_update_missing_session_is_explicit(mysql_resources) -> None:
    _, factory = mysql_resources
    repository = DiagnosisSessionRepository(factory, LocalTracer())
    with pytest.raises(ResourceNotFoundError):
        await repository.update(
            new_id(),
            DiagnosisSessionUpdate(phase=DiagnosisPhase.FAILED),
            trace_id=new_id(),
        )
