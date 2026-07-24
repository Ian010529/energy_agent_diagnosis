from energy_agent.contracts.diagnosis_components import CandidateCause
from energy_agent.guardrails.contracts import GuardrailDecision, GuardrailStatus
from energy_agent.guardrails.generation import check_generation
from energy_agent.guardrails.input import check_input
from energy_agent.guardrails.output import check_output
from energy_agent.guardrails.planning import check_plan
from energy_agent.guardrails.ports import GuardrailStatePort
from energy_agent.observability.metrics import (
    GUARDRAIL_DECISIONS,
    UNSUPPORTED_CLAIMS,
)


class GuardrailService:
    UNSAFE_GENERATION_VIOLATIONS = {
        "UNSUPPORTED_STRONG_CLAIM",
        "UNKNOWN_EVIDENCE_REFERENCE",
        "GRAPH_ONLY_STRONG_CLAIM",
    }

    @staticmethod
    def _record(layer: str, decision: GuardrailDecision) -> GuardrailDecision:
        GUARDRAIL_DECISIONS.labels(layer=layer, status=decision.status).inc()
        if "UNSUPPORTED_STRONG_CLAIM" in decision.violations:
            UNSUPPORTED_CLAIMS.labels(reason="missing_evidence").inc()
        if "GRAPH_ONLY_STRONG_CLAIM" in decision.violations:
            UNSUPPORTED_CLAIMS.labels(reason="graph_only").inc()
        return decision

    def check_input(self, state: GuardrailStatePort) -> GuardrailDecision:
        return self._record(
            "input",
            check_input(
                state.user_message or "",
                device_id=state.device_context.device_id if state.device_context else None,
                alarm_id=state.alarm_context.alarm_id if state.alarm_context else None,
                clarification_count=len(state.user_feedback),
            ),
        )

    def check_plan(self, state: GuardrailStatePort, allowed_tools: set[str]) -> GuardrailDecision:
        return self._record(
            "planning",
            check_plan(
                state.plan,
                allowed_tools=allowed_tools,
                valid_template=bool(
                    state.diagnosis_template_id and state.diagnosis_template_version
                ),
            ),
        )

    def check_generation(
        self, state: GuardrailStatePort, candidates: list[CandidateCause] | None = None
    ) -> GuardrailDecision:
        return self._record(
            "generation",
            check_generation(
                state.candidate_causes if candidates is None else candidates,
                state.evidence,
            ),
        )

    def check_output(self, state: GuardrailStatePort) -> GuardrailDecision:
        response = state.final_response or {}
        raw_safety_notes = response.get("safety_notes", [])
        safety_notes = (
            [str(item) for item in raw_safety_notes] if isinstance(raw_safety_notes, list) else []
        )
        return self._record(
            "output",
            check_output(
                summary=str(response.get("summary", "")),
                actions=state.recommended_actions,
                evidence_source_by_ref={
                    item.evidence_id: item.source_type for item in state.evidence
                },
                safety_notes=safety_notes,
            ),
        )

    def evaluate(
        self,
        state: GuardrailStatePort,
        candidates: list[CandidateCause] | None = None,
    ) -> GuardrailDecision:
        generation = self.check_generation(state, candidates)
        output = self.check_output(state)
        violations = sorted({*generation.violations, *output.violations})
        warnings = sorted({*generation.warnings, *output.warnings})
        return GuardrailDecision(
            status=(
                GuardrailStatus.BLOCKED
                if violations
                else GuardrailStatus.PASSED_WITH_WARNINGS
                if warnings
                else GuardrailStatus.PASSED
            ),
            violations=violations,
            warnings=warnings,
            blocked_actions=output.blocked_actions,
            requires_human_confirmation=output.requires_human_confirmation,
            checked_evidence_refs=generation.checked_evidence_refs,
        )

    @staticmethod
    def supported_candidates(state: GuardrailStatePort) -> list[CandidateCause]:
        return [
            candidate
            for candidate in state.candidate_causes
            if check_generation([candidate], state.evidence).status != GuardrailStatus.BLOCKED
        ]

    def sanitize_response(
        self,
        response: dict[str, object],
        decision: GuardrailDecision,
        supported_candidates: list[CandidateCause],
    ) -> dict[str, object]:
        if not self.UNSAFE_GENERATION_VIOLATIONS.intersection(decision.violations):
            return response
        raw_warnings = response.get("warnings", [])
        warnings = [str(item) for item in raw_warnings] if isinstance(raw_warnings, list) else []
        return {
            **response,
            "summary": (
                str(response.get("summary", ""))
                if supported_candidates
                else "现有证据不足以安全输出候选根因，请补充现场信息或转人工复核。"
            ),
            "candidate_causes": [item.model_dump(mode="json") for item in supported_candidates],
            "recommended_actions": (
                response.get("recommended_actions", []) if supported_candidates else []
            ),
            "recommend_ticket": (
                response.get("recommend_ticket", False) if supported_candidates else True
            ),
            "warnings": sorted({*warnings, "UNSUPPORTED_CANDIDATES_REMOVED"}),
        }
