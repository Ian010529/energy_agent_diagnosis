"""阶段 3 RAG 检索服务入口。"""

from typing import Any

from energy_agent_diagnosis.contracts import EvidencePackage, RequestContext, ToolContext
from energy_agent_diagnosis.ports.providers import ProviderLookup

from .evidence import build_evidence_package
from .query_rewrite import rewrite_query
from .recall import recall_candidates
from .rerank import rerank_candidates


async def retrieve_evidence(
    registry: ProviderLookup,
    context: ToolContext,
    request_context: RequestContext,
    settings: Any,
) -> EvidencePackage:
    """独立执行查询重写、混合召回、重排和证据包生成。"""
    query = rewrite_query(request_context)
    recall = await recall_candidates(registry, context, query, settings)
    reranked = rerank_candidates(recall.candidates, settings)
    degraded_sources = recall.degraded_sources
    if query.degraded_reason:
        degraded_sources = (*degraded_sources, query.degraded_reason)
    return build_evidence_package(
        session_id=request_context.session_id,
        trace_id=request_context.trace_id,
        candidates=reranked,
        degraded_sources=tuple(dict.fromkeys(degraded_sources)),
        settings=settings,
    )
