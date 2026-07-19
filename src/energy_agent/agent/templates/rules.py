from energy_agent.agent.state import CandidateCause, Evidence
from energy_agent.agent.templates.contracts import DiagnosisTemplate


def evaluate_candidate_rules(
    template: DiagnosisTemplate,
    evidence: list[Evidence],
    feedback: str = "",
) -> list[CandidateCause]:
    searchable = " ".join(item.summary for item in evidence) + " " + feedback
    graph_only_ids = {item.evidence_id for item in evidence if item.source_type == "graph"}
    candidates: list[CandidateCause] = []
    for rule in template.candidate_rules:
        refs = [
            item.evidence_id
            for item in evidence
            if any(term.lower() in item.summary.lower() for term in rule.evidence_terms)
        ]
        if not refs:
            if not any(term.lower() in searchable.lower() for term in rule.evidence_terms):
                continue
            refs = [item.evidence_id for item in evidence[:2]]
        only_graph = bool(refs) and set(refs).issubset(graph_only_ids)
        candidates.append(
            CandidateCause(
                cause=rule.cause,
                confidence=min(rule.base_confidence + (0.1 if feedback else 0), 0.8),
                supporting_evidence=refs,
                missing_information=rule.missing_information,
                need_manual_confirmation=True if only_graph else True,
            )
        )
    return sorted(candidates, key=lambda item: item.confidence, reverse=True)[:4]
