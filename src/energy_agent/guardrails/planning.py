from energy_agent.agent.state import PlanStep
from energy_agent.guardrails.contracts import GuardrailDecision, GuardrailStatus

WRITE_TOOLS = {"create_or_update_ticket", "write_review_result"}


def check_plan(
    plan: list[PlanStep],
    *,
    allowed_tools: set[str],
    valid_template: bool,
    max_steps: int = 16,
    max_tool_calls: int = 8,
) -> GuardrailDecision:
    violations: list[str] = []
    tools = [step.tool for step in plan if step.tool]
    if not valid_template:
        violations.append("UNREGISTERED_TEMPLATE")
    if len(plan) > max_steps:
        violations.append("PLAN_STEP_LIMIT_EXCEEDED")
    if len(tools) > max_tool_calls:
        violations.append("TOOL_CALL_LIMIT_EXCEEDED")
    if any(tool not in allowed_tools for tool in tools):
        violations.append("TOOL_NOT_ALLOWLISTED")
    if any(tool in WRITE_TOOLS for tool in tools):
        violations.append("WRITE_TOOL_AUTOMATION_BLOCKED")
    return GuardrailDecision(
        status=GuardrailStatus.BLOCKED if violations else GuardrailStatus.PASSED,
        violations=violations,
    )
