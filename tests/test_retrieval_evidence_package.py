"""验证阶段 3 标准证据包生成。"""

from energy_agent_diagnosis.core.config import RetrievalSettings
from energy_agent_diagnosis.retrieval.evidence import build_evidence_package
from energy_agent_diagnosis.retrieval.models import RetrievalCandidate


def test_evidence_package_is_traceable_and_clips_quotes() -> None:
    """证据包必须保留 trace、稳定引用 ID、分数和来源元数据。"""
    settings = RetrievalSettings(max_quote_chars=60)
    candidate = RetrievalCandidate(
        source_type="manual",
        source_id="MANUAL-PCS-017",
        content="若PCS机柜温度持续升高，应优先检查散热风扇运行状态、滤网堵塞情况和环境温度。",
        raw={"chunk_id": "chunk_0032", "page_no": 10, "chapter_title": "散热系统维护"},
        channel="manual_keyword",
        keyword_score=0.9,
        source_reliability=0.95,
        final_score=0.91,
        verified=True,
        metadata={"retrieval_channel": "manual_keyword"},
    )

    package = build_evidence_package(
        session_id="diag-1",
        trace_id="trace-1",
        candidates=[candidate],
        degraded_sources=("graph_relation",),
        settings=settings,
    )

    assert package.session_id == "diag-1"
    assert package.trace_id == "trace-1"
    assert package.package_id.startswith("pkg_")
    assert package.degraded_sources == ["graph_relation"]
    assert package.need_manual_confirmation is False
    evidence = package.ranked_evidence[0]
    assert evidence.evidence_id.startswith("evd_")
    assert evidence.chunk_id == "chunk_0032"
    assert evidence.page_number == 10
    assert evidence.section == "散热系统维护"
    assert evidence.score == 0.91
    assert len(evidence.quote_text) <= 60
    assert evidence.metadata["retrieval_channel"] == "manual_keyword"


def test_empty_or_only_weak_package_requires_manual_confirmation() -> None:
    """没有足够强证据时必须标记人工确认。"""
    settings = RetrievalSettings(min_strong_evidence_count=1)
    package = build_evidence_package(
        session_id="diag-2",
        trace_id="trace-2",
        candidates=[],
        degraded_sources=("manual_keyword", "ticket_keyword"),
        settings=settings,
    )

    assert package.need_manual_confirmation is True
    assert package.ranked_evidence == []
