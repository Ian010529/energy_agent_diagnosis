import re
from collections.abc import Awaitable, Callable

from energy_agent.retrieval.contracts import QueryRewrite

ModelRewrite = Callable[[dict[str, object]], Awaitable[object]]

DEVICE_ALIASES = {"储能变流器": "PCS", "储能柜": "PCS", "变流器": "PCS", "pcs": "PCS"}
ALARM_ALIASES = {
    "温度高": "温度告警",
    "过温": "温度告警",
    "温升": "温度告警",
    "温度异常": "温度告警",
}
COMPONENT_ALIASES = {"风扇": "散热风扇", "风机": "散热风扇"}
THERMAL_EXPANSIONS = ("散热", "散热风扇", "滤网", "风道")


def _normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _first_alias(text: str, aliases: dict[str, str]) -> str | None:
    lowered = text.lower()
    return next((standard for alias, standard in aliases.items() if alias in lowered), None)


def rule_rewrite(
    query: str,
    *,
    alarm_name: str | None = None,
    device_type: str | None = None,
    device_model: str | None = None,
    manufacturer: str | None = None,
) -> QueryRewrite:
    text = _normalize_spaces(" ".join(filter(None, (query, alarm_name or ""))))
    normalized_device = _first_alias(text, DEVICE_ALIASES) or device_type
    normalized_alarm = _first_alias(text, ALARM_ALIASES) or alarm_name or query
    component = _first_alias(text, COMPONENT_ALIASES)
    symptoms = list(
        dict.fromkeys(standard for alias, standard in ALARM_ALIASES.items() if alias in text)
    )
    identifiers = re.findall(r"\b[A-Z]{1,8}[-_]?\d{2,}[A-Z0-9_-]*\b", text, re.I)
    terms = list(
        dict.fromkeys(
            filter(
                None,
                (
                    normalized_device,
                    device_model,
                    manufacturer,
                    normalized_alarm,
                    component,
                    *symptoms,
                    *(THERMAL_EXPANSIONS if normalized_alarm == "温度告警" else ()),
                    *identifiers,
                ),
            )
        )
    )
    prefix = " ".join(filter(None, (normalized_device, device_model, normalized_alarm)))
    return QueryRewrite(
        normalized_alarm_name=normalized_alarm,
        device_type=normalized_device,
        device_model=device_model,
        manufacturer=manufacturer,
        component=component,
        symptom_terms=symptoms,
        manual_query=_normalize_spaces(f"{prefix} 原因 标准排查步骤 {' '.join(terms)}"),
        ticket_query=_normalize_spaces(f"{prefix} 故障现象 根因 处理动作 {' '.join(terms)}"),
        keyword_terms=terms,
        rewrite_mode="rules",
    )


async def rewrite_query(
    query: str,
    *,
    alarm_name: str | None = None,
    device_type: str | None = None,
    device_model: str | None = None,
    manufacturer: str | None = None,
    mode: str = "rules",
    model_rewrite: ModelRewrite | None = None,
) -> QueryRewrite:
    result = rule_rewrite(
        query,
        alarm_name=alarm_name,
        device_type=device_type,
        device_model=device_model,
        manufacturer=manufacturer,
    )
    if mode != "model_enhanced" or model_rewrite is None:
        return result
    try:
        enhanced = QueryRewrite.model_validate(await model_rewrite(result.model_dump(mode="json")))
        return enhanced.model_copy(update={"rewrite_mode": "model_enhanced"})
    except Exception:
        return result.model_copy(update={"warnings": [*result.warnings, "QUERY_REWRITE_FAILED"]})
