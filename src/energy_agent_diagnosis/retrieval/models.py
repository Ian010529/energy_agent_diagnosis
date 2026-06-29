"""阶段 3 RAG 检索链路内部模型。

这些模型只在检索模块内部流转；跨模块输出继续使用公共 ``EvidencePackage``。
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RetrievalQuery:
    """查询重写后的多路检索表达。"""

    session_id: str
    trace_id: str
    raw_query: str
    manual_query: str
    ticket_query: str
    graph_query: str
    keyword_terms: tuple[str, ...]
    filters: dict[str, Any]
    alarm_name: str | None = None
    component: str | None = None
    llm_rewrite_used: bool = False
    degraded_reason: str | None = None


@dataclass
class RetrievalCandidate:
    """统一表示手册、工单和图谱召回候选。"""

    source_type: str
    source_id: str
    content: str
    raw: dict[str, Any]
    channel: str
    keyword_score: float | None = None
    vector_score: float | None = None
    rerank_score: float | None = None
    source_reliability: float = 1.0
    final_score: float = 0.0
    weak_evidence: bool = False
    verified: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RecallResult:
    """召回阶段的候选和可降级来源。"""

    candidates: tuple[RetrievalCandidate, ...]
    degraded_sources: tuple[str, ...]
