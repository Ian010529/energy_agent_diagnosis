"""验证阶段 3 重排、分数融合、去重和多样性控制。"""

from energy_agent_diagnosis.core.config import RetrievalSettings
from energy_agent_diagnosis.retrieval.models import RetrievalCandidate
from energy_agent_diagnosis.retrieval.rerank import rerank_candidates


def test_rerank_scores_verified_strong_evidence_above_weak_graph() -> None:
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

    ranked = rerank_candidates(candidates, settings)

    assert ranked[0].source_type == "ticket"
    assert ranked[0].final_score > ranked[1].final_score


def test_rerank_deduplicates_manual_chunk_and_keeps_source_diversity() -> None:
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

    ranked = rerank_candidates(candidates, settings)

    assert len(ranked) == 2
    assert {item.source_type for item in ranked} == {"manual", "ticket"}
    assert ranked[0].content == "高分重复"
