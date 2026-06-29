"""验证阶段 3 召回编排和降级语义。"""

import pytest

from energy_agent_diagnosis.contracts import RequestContext, ToolContext
from energy_agent_diagnosis.core.config import ProviderSettings, RetrievalSettings
from energy_agent_diagnosis.providers import build_null_registry, build_provider_registry
from energy_agent_diagnosis.retrieval.query_rewrite import rewrite_query
from energy_agent_diagnosis.retrieval.recall import recall_candidates


@pytest.mark.asyncio
async def test_recall_collects_manual_ticket_and_graph_candidates() -> None:
    """混合召回应覆盖手册、工单和图谱补充来源。"""
    request = RequestContext.model_validate(
        {
            "request_id": "req-recall",
            "trace_id": "trace-recall",
            "session_id": "diag-recall",
            "source": "alarm",
            "site": {"site_id": "SITE-01"},
            "device": {
                "device_type": "PCS",
                "device_model": "SC5000",
                "manufacturer": "Sungrow",
            },
            "alarm": {"alarm_name": "PCS机柜温度持续升高"},
            "message": "PCS机柜温度持续升高 风扇 滤网",
        }
    )

    result = await recall_candidates(
        build_provider_registry(ProviderSettings()),
        ToolContext(trace_id="trace-recall", source_system="pytest"),
        rewrite_query(request),
        RetrievalSettings(score_threshold=0.1),
    )

    assert {item.source_type for item in result.candidates} >= {"manual", "ticket", "graph"}
    assert result.degraded_sources == ()


@pytest.mark.asyncio
async def test_recall_degrades_sources_without_raising() -> None:
    """Provider 无数据或未配置时，召回层应返回降级来源而不是抛异常。"""
    request = RequestContext.model_validate(
        {
            "request_id": "req-null",
            "trace_id": "trace-null",
            "session_id": "diag-null",
            "source": "alarm",
            "device": {"device_type": "PCS", "device_model": "SC5000"},
            "alarm": {"alarm_name": "PCS机柜温度持续升高"},
            "message": "PCS 温度 风扇",
        }
    )

    result = await recall_candidates(
        build_null_registry(),
        ToolContext(trace_id="trace-null", source_system="pytest"),
        rewrite_query(request),
        RetrievalSettings(),
    )

    assert result.candidates == ()
    assert set(result.degraded_sources) >= {
        "manual_keyword",
        "ticket_keyword",
        "graph_relation",
    }
