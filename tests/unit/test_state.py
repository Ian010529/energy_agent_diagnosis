from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from energy_agent.agent.state import DiagnosisState, TimeWindow, transition_state
from energy_agent.contracts.common import DiagnosisPhase, SessionSource
from energy_agent.core.errors import InvalidStateTransitionError
from energy_agent.core.ids import new_id


def state() -> DiagnosisState:
    return DiagnosisState(
        session_id=new_id(),
        run_id=new_id(),
        trace_id=new_id(),
        source=SessionSource.CHAT,
    )


def test_state_defaults_are_explicit_and_independent() -> None:
    first = state()
    second = state()
    first.warnings.append("warning")
    assert second.warnings == []


def test_valid_transition() -> None:
    updated = transition_state(state(), DiagnosisPhase.PLAN_READY)
    assert updated.phase == DiagnosisPhase.PLAN_READY


def test_terminal_transition_is_rejected() -> None:
    completed = state().model_copy(
        update={"phase": DiagnosisPhase.COMPLETED, "final_response": "done"}
    )
    with pytest.raises(InvalidStateTransitionError):
        transition_state(completed, DiagnosisPhase.INIT)


def test_need_user_input_requires_question() -> None:
    with pytest.raises(ValidationError, match="clarification"):
        DiagnosisState.model_validate(
            {**state().model_dump(), "phase": DiagnosisPhase.NEED_USER_INPUT}
        )


def test_completed_requires_final_response() -> None:
    with pytest.raises(ValidationError, match="final response"):
        DiagnosisState.model_validate({**state().model_dump(), "phase": DiagnosisPhase.COMPLETED})


def test_time_window_order() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        TimeWindow(start_time=now, end_time=now - timedelta(seconds=1))
