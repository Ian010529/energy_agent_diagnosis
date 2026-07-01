"""阶段 3 查询重写：规则标准化优先，LLM 改写失败时降级。"""

import re
from typing import Any

from energy_agent_diagnosis.contracts import RequestContext
from energy_agent_diagnosis.ports.retrieval_clients import call_qwen_rewrite

from .models import RetrievalQuery

ALARM_ALIASES = {
    "温度高": "PCS机柜温度持续升高",
    "温度持续升高": "PCS机柜温度持续升高",
    "温度告警": "PCS机柜温度持续升高",
    "风扇异常": "散热风扇异常",
    "通讯异常": "逆变器通讯中断",
    "通讯中断": "逆变器通讯中断",
    "功率异常": "逆变器输出功率异常",
    "电流异常": "电流采样异常",
    "齿轮箱温度": "齿轮箱温度偏高",
}

DEVICE_ALIASES = {
    "储能柜": "PCS",
    "储能pcs": "PCS",
    "pcs": "PCS",
    "逆变器": "inverter",
    "风机": "wind_turbine",
    "风电": "wind_turbine",
}

COMPONENT_ALIASES = {
    "风扇": "散热风扇",
    "滤网": "滤网",
    "交换机": "交换机",
    "采集器": "数据采集器",
    "传感器": "电流传感器",
    "齿轮箱": "齿轮箱",
    "冷却": "冷却回路",
}

STOP_TERMS = {"这台", "这个", "一下", "为什么", "先查什么", "帮我", "是否", "最近"}


async def rewrite_query(
    request: RequestContext,
    endpoint: str = "",
    client: Any = None,
) -> RetrievalQuery:
    """把诊断请求转换为文档约束的多路检索表达，支持 LLM 改写与规则兜底。"""
    query = _rewrite_query_rules(request)

    if not endpoint:
        return query

    headers = {"x-trace-id": request.trace_id}
    payload = {
        "message": request.message or "",
        "device_type": request.device_type or "",
        "device_model": request.device_model or "",
        "alarm_name": query.alarm_name or "",
        "component": query.component or "",
    }

    try:
        data = await call_qwen_rewrite(endpoint, payload, headers, client)
        manual_q = data.get("manual_query")
        ticket_q = data.get("ticket_query")
        graph_q = data.get("graph_query")
        kw_terms = data.get("keyword_terms")
        if (
            isinstance(manual_q, str)
            and isinstance(ticket_q, str)
            and isinstance(graph_q, str)
            and isinstance(kw_terms, list | tuple)
            and all(isinstance(t, str) for t in kw_terms)
        ):
            return RetrievalQuery(
                session_id=query.session_id,
                trace_id=query.trace_id,
                raw_query=query.raw_query,
                manual_query=manual_q,
                ticket_query=ticket_q,
                graph_query=graph_q,
                keyword_terms=tuple(kw_terms),
                filters=query.filters,
                alarm_name=query.alarm_name,
                component=query.component,
                llm_rewrite_used=True,
                degraded_reason=None,
            )
        else:
            return RetrievalQuery(
                session_id=query.session_id,
                trace_id=query.trace_id,
                raw_query=query.raw_query,
                manual_query=query.manual_query,
                ticket_query=query.ticket_query,
                graph_query=query.graph_query,
                keyword_terms=query.keyword_terms,
                filters=query.filters,
                alarm_name=query.alarm_name,
                component=query.component,
                llm_rewrite_used=False,
                degraded_reason="QWEN_REWRITE_INVALID_RESPONSE",
            )
    except TimeoutError:
        return RetrievalQuery(
            session_id=query.session_id,
            trace_id=query.trace_id,
            raw_query=query.raw_query,
            manual_query=query.manual_query,
            ticket_query=query.ticket_query,
            graph_query=query.graph_query,
            keyword_terms=query.keyword_terms,
            filters=query.filters,
            alarm_name=query.alarm_name,
            component=query.component,
            llm_rewrite_used=False,
            degraded_reason="QWEN_REWRITE_TIMEOUT",
        )
    except Exception as exc:
        # Check if HTTPStatusError / HTTPError / status_code exists on exception
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        reason = (
            f"QWEN_REWRITE_HTTP_ERROR_{status_code}"
            if status_code
            else f"QWEN_REWRITE_FAILED_{type(exc).__name__}"
        )
        return RetrievalQuery(
            session_id=query.session_id,
            trace_id=query.trace_id,
            raw_query=query.raw_query,
            manual_query=query.manual_query,
            ticket_query=query.ticket_query,
            graph_query=query.graph_query,
            keyword_terms=query.keyword_terms,
            filters=query.filters,
            alarm_name=query.alarm_name,
            component=query.component,
            llm_rewrite_used=False,
            degraded_reason=reason,
        )


def _rewrite_query_rules(request: RequestContext) -> RetrievalQuery:
    """使用规则解析多路检索查询和关键词。"""
    message = request.message or ""
    alarm_name = _normalize_alarm(request, message)
    device_type = request.device_type or _normalize_device_type(message)
    component = _normalize_component(message, alarm_name)
    keyword_terms = _keyword_terms(
        message=message,
        alarm_name=alarm_name,
        device_type=device_type,
        device_model=request.device_model,
        component=component,
    )
    filters = _filters(request, device_type, alarm_name)
    raw_query = _join_terms([message, request.device_model, alarm_name])

    manual_query = _join_terms(
        [device_type, request.device_model, alarm_name, component, "可能原因", "排查步骤"]
    )
    ticket_query = _join_terms(
        [request.device_model, alarm_name, component, "相似工单", "根因", "处理动作"]
    )
    graph_query = _join_terms([device_type, alarm_name, component, "故障原因"])
    degraded_reason = None if message.strip() else "EMPTY_MESSAGE_RULE_FALLBACK"

    return RetrievalQuery(
        session_id=request.session_id,
        trace_id=request.trace_id,
        raw_query=raw_query or _join_terms([alarm_name, device_type, request.device_model]),
        manual_query=manual_query,
        ticket_query=ticket_query,
        graph_query=graph_query,
        keyword_terms=keyword_terms,
        filters=filters,
        alarm_name=alarm_name,
        component=component,
        llm_rewrite_used=False,
        degraded_reason=degraded_reason,
    )


def _normalize_alarm(request: RequestContext, message: str) -> str | None:
    if request.alarm and request.alarm.alarm_name:
        return request.alarm.alarm_name
    for alias, standard in ALARM_ALIASES.items():
        if alias in message:
            return standard
    return None


def _normalize_device_type(message: str) -> str | None:
    lowered = message.lower()
    for alias, standard in DEVICE_ALIASES.items():
        if alias in lowered or alias in message:
            return standard
    return None


def _normalize_component(message: str, alarm_name: str | None) -> str | None:
    for alias, standard in COMPONENT_ALIASES.items():
        if alias in message:
            return standard
    if alarm_name and "温度" in alarm_name:
        return "散热风扇"
    if alarm_name and "通讯" in alarm_name:
        return "交换机"
    return None


def _filters(
    request: RequestContext,
    device_type: str | None,
    alarm_name: str | None,
) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    for key, value in (
        ("device_type", device_type),
        ("device_model", request.device_model),
        ("manufacturer", request.manufacturer),
        ("alarm_name", alarm_name),
        ("site_id", request.site_id),
    ):
        if value:
            filters[key] = value
    return filters


def _keyword_terms(
    *,
    message: str,
    alarm_name: str | None,
    device_type: str | None,
    device_model: str | None,
    component: str | None,
) -> tuple[str, ...]:
    raw_terms = re.split(r"[\s,，。！？?；;、/]+", message)
    terms = [term for term in raw_terms if term and term not in STOP_TERMS]
    terms.extend(term for term in (device_type, device_model, alarm_name, component) if term)
    unique: list[str] = []
    for term in terms:
        if term and term not in unique:
            unique.append(term)
    return tuple(unique[:12])


def _join_terms(values: list[str | None]) -> str:
    return " ".join(value for value in values if value and value.strip())
