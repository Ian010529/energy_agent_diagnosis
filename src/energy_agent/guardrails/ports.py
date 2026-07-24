from typing import Protocol

from energy_agent.contracts.diagnosis_components import (
    AlarmContext,
    CandidateCause,
    DeviceContext,
    Evidence,
    PlanStep,
    UserFeedback,
)
from energy_agent.guardrails.contracts import RecommendedAction


class GuardrailStatePort(Protocol):
    @property
    def user_message(self) -> str | None: ...

    @property
    def device_context(self) -> DeviceContext | None: ...

    @property
    def alarm_context(self) -> AlarmContext | None: ...

    @property
    def user_feedback(self) -> list[UserFeedback]: ...

    @property
    def plan(self) -> list[PlanStep]: ...

    @property
    def diagnosis_template_id(self) -> str | None: ...

    @property
    def diagnosis_template_version(self) -> str | None: ...

    @property
    def candidate_causes(self) -> list[CandidateCause]: ...

    @property
    def evidence(self) -> list[Evidence]: ...

    @property
    def final_response(self) -> dict[str, object] | None: ...

    @property
    def recommended_actions(self) -> list[RecommendedAction]: ...
