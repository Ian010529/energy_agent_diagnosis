"""阶段 3 混合召回编排。"""

from typing import Any

from energy_agent_diagnosis.contracts import ToolContext, ToolStatus
from energy_agent_diagnosis.ports.providers import ProviderLookup
from energy_agent_diagnosis.tools.stage2 import (
    query_graph_relations,
    search_manual_chunks,
    search_similar_tickets,
)

from .models import RecallResult, RetrievalCandidate, RetrievalQuery


async def recall_candidates(
    registry: ProviderLookup,
    context: ToolContext,
    query: RetrievalQuery,
    settings: Any,
) -> RecallResult:
    """执行手册、工单和图谱多路召回，并收集降级来源。"""
    candidates: list[RetrievalCandidate] = []
    degraded_sources: list[str] = []
    recall_top_k = _setting(settings, "recall_top_k", 20)

    manual_keyword = await search_manual_chunks(
        registry,
        context,
        {
            "query": " ".join(query.keyword_terms) or query.manual_query,
            "filters": _manual_filters(query.filters),
            "top_k": recall_top_k,
            "score_threshold": 0.0,
        },
    )
    _collect_manual(candidates, degraded_sources, manual_keyword, "manual_keyword")

    if _setting(settings, "enable_vector_recall", True):
        manual_vector = await search_manual_chunks(
            registry,
            context,
            {
                "query": query.manual_query,
                "filters": _manual_filters(query.filters),
                "top_k": recall_top_k,
                "score_threshold": 0.0,
            },
        )
        _collect_manual(candidates, degraded_sources, manual_vector, "manual_vector")

    ticket_keyword = await search_similar_tickets(
        registry,
        context,
        {
            "query": " ".join(query.keyword_terms) or query.ticket_query,
            "filters": query.filters,
            "verified_only": True,
            "top_k": recall_top_k,
            "score_threshold": 0.0,
        },
    )
    _collect_tickets(candidates, degraded_sources, ticket_keyword, "ticket_keyword")

    if _setting(settings, "enable_vector_recall", True):
        ticket_vector = await search_similar_tickets(
            registry,
            context,
            {
                "query": query.ticket_query,
                "filters": query.filters,
                "verified_only": True,
                "top_k": recall_top_k,
                "score_threshold": 0.0,
            },
        )
        _collect_tickets(candidates, degraded_sources, ticket_vector, "ticket_vector")

    if _setting(settings, "enable_graph_recall", True) and query.alarm_name:
        graph = await query_graph_relations(
            registry,
            context,
            {
                "alarm_name": query.alarm_name,
                "device_type": query.filters.get("device_type"),
                "component": query.component,
                "top_k": recall_top_k,
            },
        )
        _collect_graph(candidates, degraded_sources, graph)

    filtered_candidates = []
    for candidate in candidates:
        score = max(candidate.keyword_score or 0.0, candidate.vector_score or 0.0)
        if candidate.source_type == "manual":
            th = _setting(settings, "manual_score_threshold", None)
            if th is None:
                th = _setting(settings, "score_threshold", 0.45)
        elif candidate.source_type == "ticket":
            th = _setting(settings, "ticket_score_threshold", None)
            if th is None:
                th = _setting(settings, "score_threshold", 0.45)
        else:
            th = _setting(settings, "score_threshold", 0.45)
        if score >= th:
            filtered_candidates.append(candidate)

    filtered = tuple(filtered_candidates)
    return RecallResult(
        candidates=filtered or tuple(candidates),
        degraded_sources=tuple(dict.fromkeys(degraded_sources)),
    )


def _collect_manual(
    candidates: list[RetrievalCandidate],
    degraded_sources: list[str],
    result: Any,
    channel: str,
) -> None:
    if result.status is not ToolStatus.OK or not result.data:
        degraded_sources.append(channel)
        return
    chunks = result.data.get("chunks")
    if not isinstance(chunks, list):
        degraded_sources.append(channel)
        return
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        score = _score(chunk)
        candidates.append(
            RetrievalCandidate(
                source_type="manual",
                source_id=str(chunk.get("doc_id", "")),
                content=str(chunk.get("content", "")),
                raw=chunk,
                channel=channel,
                keyword_score=score if channel.endswith("keyword") else None,
                vector_score=score if channel.endswith("vector") else None,
                verified=True,
                metadata={"retrieval_channel": channel},
            )
        )


def _collect_tickets(
    candidates: list[RetrievalCandidate],
    degraded_sources: list[str],
    result: Any,
    channel: str,
) -> None:
    if result.status is not ToolStatus.OK or not result.data:
        degraded_sources.append(channel)
        return
    tickets = result.data.get("tickets")
    if not isinstance(tickets, list):
        degraded_sources.append(channel)
        return
    for ticket in tickets:
        if not isinstance(ticket, dict):
            continue
        score = _score(ticket)
        content = " ".join(
            str(ticket.get(field, ""))
            for field in ("fault_symptom", "root_cause", "action_taken")
            if ticket.get(field)
        )
        verified = ticket.get("is_verified") is True
        candidates.append(
            RetrievalCandidate(
                source_type="ticket",
                source_id=str(ticket.get("ticket_id", "")),
                content=content,
                raw=ticket,
                channel=channel,
                keyword_score=score if channel.endswith("keyword") else None,
                vector_score=score if channel.endswith("vector") else None,
                weak_evidence=not verified,
                verified=verified,
                metadata={"retrieval_channel": channel},
            )
        )


def _collect_graph(
    candidates: list[RetrievalCandidate],
    degraded_sources: list[str],
    result: Any,
) -> None:
    if result.status is not ToolStatus.OK or not result.data:
        degraded_sources.append("graph_relation")
        return
    relations = result.data.get("relations")
    if not isinstance(relations, list):
        degraded_sources.append("graph_relation")
        return
    for relation in relations:
        if not isinstance(relation, dict):
            continue
        content = " ".join(
            str(relation.get(field, ""))
            for field in ("fault_cause", "component", "action")
            if relation.get(field)
        )
        candidates.append(
            RetrievalCandidate(
                source_type="graph",
                source_id=str(relation.get("relation_id", "")),
                content=content,
                raw=relation,
                channel="graph_relation",
                keyword_score=_score(relation),
                weak_evidence=True,
                verified=relation.get("verified") is True,
                metadata={"retrieval_channel": "graph_relation"},
            )
        )


def _score(record: dict[str, Any]) -> float:
    value = record.get("score", record.get("confidence", 0.0))
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0.0


def _base_score(candidate: RetrievalCandidate) -> float:
    return max(candidate.keyword_score or 0.0, candidate.vector_score or 0.0)


def _setting(settings: Any, name: str, default: Any) -> Any:
    value = getattr(settings, name, default)
    return default if value is None else value


def _manual_filters(filters: dict[str, Any]) -> dict[str, Any]:
    """手册 chunk 没有告警和场站字段，召回时只保留文档元数据过滤。"""
    return {
        key: value
        for key, value in filters.items()
        if key in {"device_type", "device_model", "manufacturer"}
    }
