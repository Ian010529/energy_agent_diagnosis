from energy_agent.guardrails.contracts import (
    GuardrailDecision,
    GuardrailStatus,
    RecommendedAction,
)


def check_output(
    *,
    summary: str,
    actions: list[RecommendedAction],
    evidence_source_by_ref: dict[str, str],
    safety_notes: list[str],
) -> GuardrailDecision:
    violations: list[str] = []
    blocked: list[str] = []
    for action in actions:
        if action.risk_level.value not in {"high", "critical"}:
            continue
        source_types = {
            evidence_source_by_ref[ref]
            for ref in action.evidence_refs
            if ref in evidence_source_by_ref
            and evidence_source_by_ref[ref] not in {"graph", "device", "alarm"}
        }
        if (
            not action.requires_human_confirmation
            or len(source_types) < 2
            or not safety_notes
            or action.execution_status.value != "not_executed"
        ):
            violations.append("HIGH_RISK_ACTION_UNSAFE")
            blocked.append(action.action_id)
    if not summary.strip():
        violations.append("EMPTY_SUMMARY")
    return GuardrailDecision(
        status=GuardrailStatus.BLOCKED if violations else GuardrailStatus.PASSED,
        violations=sorted(set(violations)),
        blocked_actions=blocked,
        requires_human_confirmation=bool(
            [item for item in actions if item.requires_human_confirmation]
        ),
    )
