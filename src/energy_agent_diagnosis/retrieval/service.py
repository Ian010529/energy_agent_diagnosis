"""阶段 3 RAG 检索服务入口。"""

from datetime import timedelta
from typing import Any, cast

from energy_agent_diagnosis.contracts import EvidencePackage, RequestContext, ToolContext
from energy_agent_diagnosis.ports.providers import (
    ProviderLookup,
    ProviderName,
    TimeseriesProvider,
)

from .evidence import build_evidence_package
from .models import RetrievalCandidate
from .query_rewrite import rewrite_query
from .recall import recall_candidates
from .rerank import rerank_candidates


async def retrieve_evidence(
    registry: ProviderLookup,
    context: ToolContext,
    request_context: RequestContext,
    settings: Any,
    client: Any = None,
) -> EvidencePackage:
    """独立执行查询重写、混合召回、重排和证据包生成。"""
    retrieval_settings = getattr(settings, "retrieval", settings)

    # 1. Query Rewrite
    qwen_endpoint = getattr(retrieval_settings, "qwen_rewrite_endpoint", "")
    query = await rewrite_query(request_context, endpoint=qwen_endpoint, client=client)

    # 2. Hybrid Recall
    recall = await recall_candidates(registry, context, query, retrieval_settings)

    degraded_sources = list(recall.degraded_sources)
    if query.degraded_reason:
        degraded_sources.append(query.degraded_reason)

    # 3. Timeseries summary integration
    device_id = request_context.device_id
    timeseries_expected = bool(device_id and request_context.alarm)
    timeseries_trigger_time = request_context.alarm.trigger_time if request_context.alarm else None

    recalled_candidates = list(recall.candidates)
    if timeseries_expected:
        if timeseries_trigger_time:
            start_time = (timeseries_trigger_time - timedelta(minutes=15)).isoformat()
            end_time = (timeseries_trigger_time + timedelta(minutes=15)).isoformat()

            ts_payload: dict[str, Any] = {
                "device_id": device_id,
                "start_time": start_time,
                "end_time": end_time,
                "metrics": [],
            }
            try:
                timeseries_provider = cast(
                    TimeseriesProvider,
                    registry.get(ProviderName.TIMESERIES),
                )
                ts_result = await timeseries_provider.query_timeseries_window(context, ts_payload)
                if ts_result.success and ts_result.data:
                    content = _format_timeseries_content(ts_result.data)
                    recalled_candidates.append(
                        RetrievalCandidate(
                            source_type="timeseries",
                            source_id=str(device_id),
                            content=content,
                            raw=ts_result.data,
                            channel="timeseries",
                            keyword_score=0.70,
                            vector_score=None,
                            rerank_score=None,
                            weak_evidence=True,
                            verified=False,
                            metadata={
                                "retrieval_channel": "timeseries",
                                "source_group": "timeseries",
                                "raw_record_snapshot": ts_result.data,
                            },
                        )
                    )
                else:
                    degraded_sources.append("timeseries")
            except Exception:
                degraded_sources.append("timeseries")
        else:
            degraded_sources.append("timeseries")

    # 4. Rerank Candidates
    reranked = await rerank_candidates(
        recalled_candidates,
        retrieval_settings,
        client=client,
        trace_id=request_context.trace_id,
        query_text=query.raw_query,
        degraded_sources=degraded_sources,
    )

    return build_evidence_package(
        session_id=request_context.session_id,
        trace_id=request_context.trace_id,
        candidates=reranked,
        degraded_sources=tuple(dict.fromkeys(degraded_sources)),
        settings=retrieval_settings,
    )


def _format_timeseries_content(data: dict[str, Any]) -> str:
    metrics = data.get("metrics", [])
    parts = []
    for m in metrics:
        name = m.get("metric_name", "")
        m_min = m.get("min", "")
        m_max = m.get("max", "")
        m_avg = m.get("avg", "")
        trend = m.get("trend", "")
        parts.append(f"{name}: min={m_min}, max={m_max}, avg={m_avg}, trend={trend}")
    return "Timeseries Summary - " + "; ".join(parts)
