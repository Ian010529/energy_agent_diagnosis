"""验证阶段 3 RAG 检索服务端到端闭环。"""

import pytest

from energy_agent_diagnosis.contracts import RequestContext, ToolContext
from energy_agent_diagnosis.core.config import ProviderSettings, RetrievalSettings
from energy_agent_diagnosis.providers import build_provider_registry
from energy_agent_diagnosis.retrieval.service import retrieve_evidence


def request_context(
    *,
    session_id: str,
    trace_id: str,
    device_type: str,
    device_model: str,
    manufacturer: str,
    site_id: str,
    alarm_name: str,
    message: str,
) -> RequestContext:
    """构造阶段 3 典型告警检索请求。"""
    return RequestContext.model_validate(
        {
            "request_id": f"req-{session_id}",
            "trace_id": trace_id,
            "session_id": session_id,
            "source": "alarm",
            "site": {"site_id": site_id},
            "device": {
                "device_type": device_type,
                "device_model": device_model,
                "manufacturer": manufacturer,
            },
            "alarm": {"alarm_name": alarm_name},
            "message": message,
        }
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("rag_request", "expected_terms"),
    [
        (
            request_context(
                session_id="diag-pcs-temp",
                trace_id="trace-pcs-temp",
                device_type="PCS",
                device_model="SC5000",
                manufacturer="Sungrow",
                site_id="SITE-01",
                alarm_name="PCS机柜温度持续升高",
                message="PCS机柜温度持续升高，风扇转速异常，先查什么？",
            ),
            {"manual": "散热", "ticket": "散热风扇"},
        ),
        (
            request_context(
                session_id="diag-inv-comm",
                trace_id="trace-inv-comm",
                device_type="inverter",
                device_model="SUN2000-100KTL",
                manufacturer="Huawei",
                site_id="SITE-01",
                alarm_name="逆变器通讯中断",
                message="逆变器通讯中断，采集器和交换机怎么排查？",
            ),
            {"manual": "通讯", "ticket": "交换机"},
        ),
        (
            request_context(
                session_id="diag-wt-temp",
                trace_id="trace-wt-temp",
                device_type="wind_turbine",
                device_model="GW155-3.3MW",
                manufacturer="Goldwind",
                site_id="SITE-03",
                alarm_name="齿轮箱温度偏高",
                message="风机齿轮箱温度偏高，冷却回路是否异常？",
            ),
            {"manual": "齿轮箱", "ticket": "冷却"},
        ),
    ],
)
async def test_retrieve_evidence_recalls_manual_and_ticket_for_typical_alarms(
    rag_request: RequestContext,
    expected_terms: dict[str, str],
) -> None:
    """至少三类典型告警应稳定召回手册和相似工单。"""
    registry = build_provider_registry(ProviderSettings())
    context = ToolContext(trace_id=rag_request.trace_id, source_system="pytest")
    settings = RetrievalSettings(score_threshold=0.1, final_top_k=5)

    package = await retrieve_evidence(registry, context, rag_request, settings)

    source_types = {item.source_type for item in package.ranked_evidence}
    quotes = "\n".join(item.quote_text for item in package.ranked_evidence)
    assert package.trace_id == rag_request.trace_id
    assert package.session_id == rag_request.session_id
    assert {"manual", "ticket"}.issubset(source_types)
    assert expected_terms["manual"] in quotes
    assert expected_terms["ticket"] in quotes
    assert all(item.evidence_id for item in package.ranked_evidence)
    assert all(0 <= item.score <= 1 for item in package.ranked_evidence)
    assert package.need_manual_confirmation is False


@pytest.mark.asyncio
async def test_retrieve_evidence_records_rewrite_degradation_for_empty_message() -> None:
    """查询重写降级应进入证据包 degraded_sources，且不阻断召回。"""
    registry = build_provider_registry(ProviderSettings())
    request = request_context(
        session_id="diag-empty",
        trace_id="trace-empty",
        device_type="PCS",
        device_model="SC5000",
        manufacturer="Sungrow",
        site_id="SITE-01",
        alarm_name="PCS机柜温度持续升高",
        message="",
    )

    package = await retrieve_evidence(
        registry,
        ToolContext(trace_id="trace-empty", source_system="pytest"),
        request,
        RetrievalSettings(score_threshold=0.1),
    )

    assert "EMPTY_MESSAGE_RULE_FALLBACK" in package.degraded_sources
    assert package.ranked_evidence
