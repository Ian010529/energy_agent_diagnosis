import re

from energy_agent.guardrails.contracts import GuardrailDecision, GuardrailStatus

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_INJECTION = re.compile(
    r"(忽略.{0,12}(系统|之前).{0,12}指令|泄露.{0,8}(提示|prompt)|"
    r"伪造.{0,8}system|调用.{0,8}(内部)?tool)",
    re.IGNORECASE,
)
_QUERY = re.compile(r"\b(select|insert|update|delete|drop|match)\b|from\s*\(|\|>", re.IGNORECASE)
_HIGH_RISK_COMMAND = re.compile(
    r"(立即|马上|请|执行|自动|远程).{0,8}"
    r"(停机|断电|合闸|分闸|回路切换|保护旁路|修改保护参数|解除联锁|高压设备.{0,4}复位)"
)
_RISK_ASSESSMENT = re.compile(
    r"(?:判断|评估|分析|确认).{0,4}(?:是否|有无|需不需要)|"
    r"是否(?:存在|需要|应当|应该|有必要)?"
)


def _contains_high_risk_command(message: str) -> bool:
    for match in _HIGH_RISK_COMMAND.finditer(message):
        prefix = message[max(0, match.start() - 16) : match.start()]
        if any(
            negation in prefix
            for negation in ("没有", "未", "尚未", "禁止", "不要", "不得", "不应", "无需", "避免")
        ):
            continue
        context = message[max(0, match.start() - 16) : match.end()]
        if _RISK_ASSESSMENT.search(context):
            continue
        return True
    return False


def check_input(
    message: str,
    *,
    device_id: str | None = None,
    alarm_id: str | None = None,
    clarification_count: int = 0,
    max_length: int = 8_000,
) -> GuardrailDecision:
    violations: list[str] = []
    warnings: list[str] = []
    if not message.strip():
        violations.append("EMPTY_MESSAGE")
    if len(message) > max_length:
        violations.append("MESSAGE_TOO_LONG")
    if _CONTROL.search(message):
        violations.append("ILLEGAL_CONTROL_CHARACTER")
    if clarification_count > 3:
        violations.append("TOO_MANY_CLARIFICATIONS")
    if device_id and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", device_id):
        violations.append("INVALID_DEVICE_ID")
    if alarm_id and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", alarm_id):
        violations.append("INVALID_ALARM_ID")
    if _QUERY.search(message):
        violations.append("CLIENT_QUERY_LANGUAGE_BLOCKED")
    if _contains_high_risk_command(message):
        violations.append("HIGH_RISK_DEVICE_COMMAND_BLOCKED")
    if _INJECTION.search(message):
        warnings.append("PROMPT_INJECTION_DETECTED")
    return GuardrailDecision(
        status=GuardrailStatus.BLOCKED
        if violations
        else GuardrailStatus.PASSED_WITH_WARNINGS
        if warnings
        else GuardrailStatus.PASSED,
        violations=violations,
        warnings=warnings,
    )
