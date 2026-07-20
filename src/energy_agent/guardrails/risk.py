import re

from energy_agent.contracts.common import RiskLevel

HIGH_RISK_PATTERN = re.compile(
    r"(停机|断电|合闸|分闸|回路切换|保护旁路|保护参数修改|解除联锁|高压设备.*复位)"
)


def classify_action(description: str) -> RiskLevel:
    return RiskLevel.HIGH if HIGH_RISK_PATTERN.search(description) else RiskLevel.LOW
