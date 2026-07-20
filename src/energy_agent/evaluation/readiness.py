from typing import Literal

ReadinessDecision = Literal["GO", "CONDITIONAL_GO", "NO_GO"]


def decide_readiness(
    *,
    technical_gate_passed: bool,
    business_thresholds_configured: bool,
    business_gate_passed: bool,
    major_risks_open: bool,
    real_manuals_accepted: bool,
    external_live_validation_passed: bool,
    waiver_active: bool,
) -> ReadinessDecision:
    if not technical_gate_passed or major_risks_open:
        return "NO_GO"
    if (
        business_thresholds_configured
        and business_gate_passed
        and real_manuals_accepted
        and external_live_validation_passed
        and not waiver_active
    ):
        return "GO"
    return "CONDITIONAL_GO"
