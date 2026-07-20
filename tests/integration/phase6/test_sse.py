import pytest

from energy_agent.agent.events import QueueDiagnosisEventEmitter
from energy_agent.agent.state import DiagnosisState
from energy_agent.contracts.common import SessionSource
from energy_agent.contracts.events import SSEEventType

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_queue_emitter_has_real_run_metadata_and_sequence() -> None:
    emitter = QueueDiagnosisEventEmitter()
    state = DiagnosisState(session_id="s", run_id="r", trace_id="t", source=SessionSource.ALARM)
    await emitter.emit(SSEEventType.INTENT_IDENTIFIED, state, intent="fault_diagnosis")
    await emitter.close()
    events = [item async for item in emitter.events()]
    assert events[0].event_sequence == 1
    assert events[0].run_id == "r"
