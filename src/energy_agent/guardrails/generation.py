from energy_agent.agent.state import CandidateCause, Evidence
from energy_agent.guardrails.contracts import GuardrailDecision, GuardrailStatus


def check_generation(
    candidates: list[CandidateCause], evidence: list[Evidence]
) -> GuardrailDecision:
    known = {item.evidence_id for item in evidence}
    violations: list[str] = []
    for cause in candidates:
        if not cause.supporting_evidence:
            violations.append("UNSUPPORTED_STRONG_CLAIM")
        elif any(ref not in known for ref in cause.supporting_evidence):
            violations.append("UNKNOWN_EVIDENCE_REFERENCE")
        elif all(ref.startswith("graph:") for ref in cause.supporting_evidence):
            violations.append("GRAPH_ONLY_STRONG_CLAIM")
    return GuardrailDecision(
        status=GuardrailStatus.BLOCKED if violations else GuardrailStatus.PASSED,
        violations=sorted(set(violations)),
        checked_evidence_refs=sorted(known),
    )
