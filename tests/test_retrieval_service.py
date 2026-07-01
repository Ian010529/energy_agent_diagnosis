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


@pytest.mark.asyncio
async def test_qwen_rewrite_success() -> None:
    from unittest.mock import AsyncMock

    from energy_agent_diagnosis.retrieval.query_rewrite import rewrite_query

    request = request_context(
        session_id="diag-qwen",
        trace_id="trace-qwen",
        device_type="PCS",
        device_model="SC5000",
        manufacturer="Sungrow",
        site_id="SITE-01",
        alarm_name="PCS机柜温度持续升高",
        message="温度高",
    )

    mock_client = AsyncMock()
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "manual_query": "LLM manual query",
        "ticket_query": "LLM ticket query",
        "graph_query": "LLM graph query",
        "keyword_terms": ["LLM", "keyword"],
    }
    mock_client.post.return_value = mock_response

    query = await rewrite_query(request, endpoint="http://qwen-rewrite", client=mock_client)

    assert query.llm_rewrite_used is True
    assert query.manual_query == "LLM manual query"
    assert query.ticket_query == "LLM ticket query"
    assert query.graph_query == "LLM graph query"
    assert query.keyword_terms == ("LLM", "keyword")
    assert query.degraded_reason is None


@pytest.mark.asyncio
async def test_qwen_rewrite_fallback() -> None:
    from unittest.mock import AsyncMock

    import httpx

    from energy_agent_diagnosis.retrieval.query_rewrite import rewrite_query

    request = request_context(
        session_id="diag-qwen-fail",
        trace_id="trace-qwen-fail",
        device_type="PCS",
        device_model="SC5000",
        manufacturer="Sungrow",
        site_id="SITE-01",
        alarm_name="PCS机柜温度持续升高",
        message="温度高",
    )

    mock_client = AsyncMock()
    mock_client.post.side_effect = httpx.TimeoutException("Timeout")

    query = await rewrite_query(request, endpoint="http://qwen-rewrite", client=mock_client)

    assert query.llm_rewrite_used is False
    assert query.degraded_reason == "QWEN_REWRITE_TIMEOUT"
    assert query.manual_query != "LLM manual query"


@pytest.mark.asyncio
async def test_reranker_success_and_fallback() -> None:
    from unittest.mock import AsyncMock

    from energy_agent_diagnosis.retrieval.models import RetrievalCandidate
    from energy_agent_diagnosis.retrieval.rerank import rerank_candidates

    candidates = [
        RetrievalCandidate(
            source_type="manual",
            source_id="M-1",
            content="Content 1",
            raw={},
            channel="manual_keyword",
            keyword_score=0.8,
        )
    ]

    settings = RetrievalSettings(reranker_endpoint="http://reranker")
    mock_client = AsyncMock()
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [0.95]
    mock_client.post.return_value = mock_response

    ranked = await rerank_candidates(candidates, settings, client=mock_client)
    assert len(ranked) == 1
    assert ranked[0].rerank_score == 0.95

    mock_client.post.side_effect = Exception("error")
    degraded = []
    ranked_fb = await rerank_candidates(
        candidates,
        settings,
        client=mock_client,
        degraded_sources=degraded,
    )
    assert len(ranked_fb) == 1
    assert ranked_fb[0].rerank_score is None
    assert "RERANKER_FAILED_Exception" in degraded


@pytest.mark.asyncio
async def test_timeseries_summary_inclusion_and_degradation() -> None:
    from energy_agent_diagnosis.contracts import RequestContext
    from energy_agent_diagnosis.providers import build_provider_registry
    from energy_agent_diagnosis.retrieval.service import retrieve_evidence

    registry = build_provider_registry(ProviderSettings())
    request = RequestContext.model_validate(
        {
            "request_id": "req-ts-ok",
            "trace_id": "trace-ts-ok",
            "session_id": "session-ts-ok",
            "source": "alarm",
            "device_id": "PCS-10086",
            "device": {"device_type": "PCS", "device_model": "SC5000"},
            "alarm": {
                "alarm_name": "PCS机柜温度持续升高",
                "trigger_time": "2026-06-26T10:05:00+08:00",
            },
            "message": "test",
        }
    )

    settings = RetrievalSettings(score_threshold=0.1, final_top_k=5)
    package = await retrieve_evidence(
        registry,
        ToolContext(trace_id="t1", source_system="test"),
        request,
        settings,
    )

    ts_evidences = [item for item in package.ranked_evidence if item.source_type == "timeseries"]
    assert len(ts_evidences) == 1
    assert ts_evidences[0].source_id == "PCS-10086"
    assert "cabinet_temperature" in ts_evidences[0].quote_text
    assert ts_evidences[0].score > 0
    assert len(package.ranked_evidence) <= settings.final_top_k

    request_no_time = RequestContext.model_validate(
        {
            "request_id": "req-ts-deg",
            "trace_id": "trace-ts-deg",
            "session_id": "session-ts-deg",
            "source": "alarm",
            "device_id": "PCS-10086",
            "device": {"device_type": "PCS", "device_model": "SC5000"},
            "alarm": {
                "alarm_name": "PCS机柜温度持续升高",
            },
            "message": "test",
        }
    )
    package_deg = await retrieve_evidence(
        registry,
        ToolContext(trace_id="t2", source_system="test"),
        request_no_time,
        settings,
    )
    assert "timeseries" in package_deg.degraded_sources


@pytest.mark.asyncio
async def test_timeseries_candidate_is_sent_to_reranker() -> None:
    """时序摘要应作为统一候选进入 reranker 入参。"""
    from unittest.mock import AsyncMock

    from energy_agent_diagnosis.contracts import RequestContext
    from energy_agent_diagnosis.providers import build_provider_registry
    from energy_agent_diagnosis.retrieval.service import retrieve_evidence

    registry = build_provider_registry(ProviderSettings())
    request = RequestContext.model_validate(
        {
            "request_id": "req-ts-rerank",
            "trace_id": "trace-ts-rerank",
            "session_id": "session-ts-rerank",
            "source": "alarm",
            "device_id": "PCS-10086",
            "device": {"device_type": "PCS", "device_model": "SC5000"},
            "alarm": {
                "alarm_name": "PCS机柜温度持续升高",
                "trigger_time": "2026-06-26T10:05:00+08:00",
            },
            "message": "PCS机柜温度持续升高",
        }
    )
    mock_client = AsyncMock()
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"scores": []}
    mock_client.post.return_value = mock_response

    await retrieve_evidence(
        registry,
        ToolContext(trace_id="t-rerank", source_system="test"),
        request,
        RetrievalSettings(
            score_threshold=0.1,
            final_top_k=5,
            reranker_endpoint="http://reranker",
        ),
        client=mock_client,
    )

    reranker_payload = mock_client.post.call_args.kwargs["json"]
    pair_texts = [pair["text"] for pair in reranker_payload["pairs"]]
    assert any("cabinet_temperature" in text for text in pair_texts)


@pytest.mark.asyncio
async def test_real_adapters_and_registry_config() -> None:
    from unittest.mock import AsyncMock

    import httpx

    from energy_agent_diagnosis.contracts import ToolContext, ToolStatus
    from energy_agent_diagnosis.providers.graph_relation.real import RealGraphRelationProvider
    from energy_agent_diagnosis.providers.manual_search.real import RealManualSearchProvider
    from energy_agent_diagnosis.providers.ticket_search.real import RealTicketSearchProvider

    context = ToolContext(trace_id="t", source_system="test")

    mock_client = AsyncMock()
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "chunks": [{"content": "manual info", "score": 0.88}],
        "tickets": [{"ticket_id": "T-1", "is_verified": True, "score": 0.9}],
        "relations": [{"alarm_name": "PCS", "confidence": 0.95, "score": 0.9}],
    }
    mock_client.post.return_value = mock_resp

    p_manual = RealManualSearchProvider(endpoint="http://manual", client=mock_client)
    res_m = await p_manual.search_manual_chunks(context, {"query": "q"})
    assert res_m.success is True
    assert res_m.status is ToolStatus.OK
    assert res_m.data["chunks"][0]["content"] == "manual info"

    p_ticket = RealTicketSearchProvider(endpoint="http://ticket", client=mock_client)
    res_t = await p_ticket.search_similar_tickets(context, {"query": "q"})
    assert res_t.success is True
    assert res_t.data["tickets"][0]["ticket_id"] == "T-1"

    p_graph = RealGraphRelationProvider(endpoint="http://graph", client=mock_client)
    res_g = await p_graph.query_graph_relations(context, {"alarm_name": "PCS"})
    assert res_g.success is True
    assert res_g.data["relations"][0]["alarm_name"] == "PCS"

    mock_client.post.side_effect = httpx.TimeoutException("timeout")
    res_m_to = await p_manual.search_manual_chunks(context, {"query": "q"})
    assert res_m_to.success is False
    assert res_m_to.status is ToolStatus.TIMEOUT

    from energy_agent_diagnosis.core.config import ProviderSettings, RetrievalSettings
    from energy_agent_diagnosis.providers import build_provider_registry

    prov_settings = ProviderSettings(manual_search="real")
    ret_settings = RetrievalSettings(manual_search_endpoint="")
    with pytest.raises(ValueError, match="尚未实现 Real Provider"):
        build_provider_registry(prov_settings, ret_settings)

    ret_settings_ok = RetrievalSettings(manual_search_endpoint="http://endpoint")
    reg = build_provider_registry(prov_settings, ret_settings_ok)
    assert reg.get("manual_search").__class__.__name__ == "RealManualSearchProvider"
