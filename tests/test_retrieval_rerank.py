"""验证阶段 3 重排、分数融合、去重和多样性控制。"""

import pytest

from energy_agent_diagnosis.core.config import RetrievalSettings
from energy_agent_diagnosis.retrieval.models import RetrievalCandidate
from energy_agent_diagnosis.retrieval.rerank import rerank_candidates


@pytest.mark.asyncio
async def test_rerank_scores_verified_strong_evidence_above_weak_graph() -> None:
    """已审核强证据应优先于图谱弱证据。"""
    settings = RetrievalSettings(final_top_k=3)
    candidates = [
        RetrievalCandidate(
            source_type="graph",
            source_id="GRAPH-1",
            content="风扇失效 检查风扇",
            raw={"relation_id": "GRAPH-1"},
            channel="graph_relation",
            keyword_score=0.9,
            weak_evidence=True,
            verified=True,
        ),
        RetrievalCandidate(
            source_type="ticket",
            source_id="TICKET-1",
            content="风扇转速为0 更换风扇",
            raw={"ticket_id": "TICKET-1"},
            channel="ticket_keyword",
            keyword_score=0.8,
            verified=True,
        ),
    ]

    ranked = await rerank_candidates(candidates, settings)

    assert ranked[0].source_type == "ticket"
    assert ranked[0].final_score > ranked[1].final_score


@pytest.mark.asyncio
async def test_rerank_deduplicates_manual_chunk_and_keeps_source_diversity() -> None:
    """重复 chunk 只保留高分项，最终结果保留不同来源。"""
    settings = RetrievalSettings(final_top_k=3)
    candidates = [
        RetrievalCandidate(
            source_type="manual",
            source_id="MANUAL-1",
            content="低分重复",
            raw={"chunk_id": "chunk-1"},
            channel="manual_keyword",
            keyword_score=0.4,
            verified=True,
        ),
        RetrievalCandidate(
            source_type="manual",
            source_id="MANUAL-1",
            content="高分重复",
            raw={"chunk_id": "chunk-1"},
            channel="manual_vector",
            vector_score=0.9,
            verified=True,
        ),
        RetrievalCandidate(
            source_type="ticket",
            source_id="TICKET-1",
            content="相似工单",
            raw={"ticket_id": "TICKET-1"},
            channel="ticket_keyword",
            keyword_score=0.8,
            verified=True,
        ),
    ]

    ranked = await rerank_candidates(candidates, settings)

    assert len(ranked) == 2
    assert {item.source_type for item in ranked} == {"manual", "ticket"}
    assert ranked[0].content == "高分重复"
    assert ranked[0].keyword_score == 0.4
    assert ranked[0].vector_score == 0.9
    assert ranked[0].metadata["merged_channels"] == ["manual_keyword", "manual_vector"]


@pytest.mark.asyncio
async def test_rerank_merges_ticket_keyword_and_vector_channels() -> None:
    """同一工单的关键词和向量召回应合并后再统一评分。"""
    settings = RetrievalSettings(final_top_k=2)
    candidates = [
        RetrievalCandidate(
            source_type="ticket",
            source_id="TICKET-1",
            content="关键词召回工单",
            raw={"ticket_id": "TICKET-1"},
            channel="ticket_keyword",
            keyword_score=0.5,
            verified=True,
        ),
        RetrievalCandidate(
            source_type="ticket",
            source_id="TICKET-1",
            content="向量召回工单",
            raw={"ticket_id": "TICKET-1"},
            channel="ticket_vector",
            vector_score=0.8,
            verified=True,
        ),
    ]

    ranked = await rerank_candidates(candidates, settings)

    assert len(ranked) == 1
    assert ranked[0].keyword_score == 0.5
    assert ranked[0].vector_score == 0.8
    assert ranked[0].metadata["merged_channels"] == ["ticket_keyword", "ticket_vector"]


@pytest.mark.asyncio
async def test_rerank_respects_final_top_k_when_preserving_timeseries() -> None:
    """来源多样性控制不能突破 final_top_k。"""
    settings = RetrievalSettings(final_top_k=2)
    candidates = [
        RetrievalCandidate(
            source_type="manual",
            source_id="M-1",
            content="手册证据",
            raw={"chunk_id": "M-1"},
            channel="manual_keyword",
            keyword_score=0.9,
            verified=True,
        ),
        RetrievalCandidate(
            source_type="ticket",
            source_id="T-1",
            content="工单证据",
            raw={"ticket_id": "T-1"},
            channel="ticket_keyword",
            keyword_score=0.8,
            verified=True,
        ),
        RetrievalCandidate(
            source_type="timeseries",
            source_id="D-1",
            content="时序摘要",
            raw={"metrics": []},
            channel="timeseries",
            keyword_score=0.7,
            weak_evidence=True,
        ),
    ]

    ranked = await rerank_candidates(candidates, settings)

    assert len(ranked) == 2
