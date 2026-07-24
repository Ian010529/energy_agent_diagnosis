from energy_agent.contracts.common import StrictModel
from energy_agent.contracts.diagnosis_components import CandidateCause, ClarificationQuestion


class CandidateCauseEnvelope(StrictModel):
    candidate_causes: list[CandidateCause]


class ClarificationEnvelope(StrictModel):
    clarification_questions: list[ClarificationQuestion]
