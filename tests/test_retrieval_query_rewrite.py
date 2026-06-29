"""验证阶段 3 查询重写符合 RAG 文档约束。"""

from energy_agent_diagnosis.contracts import RequestContext
from energy_agent_diagnosis.retrieval.query_rewrite import rewrite_query


def test_rewrite_query_generates_filters_and_multi_route_queries() -> None:
    """告警上下文应被标准化为手册、工单和图谱三路 query。"""
    request = RequestContext.model_validate(
        {
            "request_id": "req-1",
            "trace_id": "trace-1",
            "session_id": "diag-1",
            "source": "alarm",
            "site": {"site_id": "SITE-01"},
            "device": {
                "device_id": "PCS-10086",
                "device_type": "PCS",
                "device_model": "SC5000",
                "manufacturer": "Sungrow",
            },
            "alarm": {"alarm_name": "PCS机柜温度持续升高"},
            "message": "这台储能柜温度高，先查风扇还是滤网？",
        }
    )

    query = rewrite_query(request)

    assert query.filters == {
        "device_type": "PCS",
        "device_model": "SC5000",
        "manufacturer": "Sungrow",
        "alarm_name": "PCS机柜温度持续升高",
        "site_id": "SITE-01",
    }
    assert query.alarm_name == "PCS机柜温度持续升高"
    assert query.component == "散热风扇"
    assert "排查步骤" in query.manual_query
    assert "相似工单" in query.ticket_query
    assert "故障原因" in query.graph_query
    assert "SC5000" in query.keyword_terms


def test_rewrite_query_falls_back_when_message_is_empty() -> None:
    """没有自然语言消息时，规则字段仍能形成可检索表达。"""
    request = RequestContext.model_validate(
        {
            "request_id": "req-2",
            "trace_id": "trace-2",
            "session_id": "diag-2",
            "source": "alarm",
            "device": {"device_type": "inverter", "device_model": "SUN2000-100KTL"},
            "alarm": {"alarm_name": "逆变器通讯中断"},
        }
    )

    query = rewrite_query(request)

    assert query.degraded_reason == "EMPTY_MESSAGE_RULE_FALLBACK"
    assert query.manual_query
    assert query.ticket_query
    assert query.graph_query
