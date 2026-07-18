from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from energy_agent.contracts.common import StrictModel


class RetrievalMode(StrEnum):
    HYBRID = "hybrid"
    KEYWORD_ONLY = "keyword_only"
    VECTOR_ONLY = "vector_only"


class SourceType(StrEnum):
    MANUAL = "manual"
    TICKET = "ticket"


class QueryRewrite(StrictModel):
    normalized_alarm_name: str
    device_type: str | None = None
    device_model: str | None = None
    manufacturer: str | None = None
    component: str | None = None
    symptom_terms: list[str] = Field(default_factory=list)
    manual_query: str
    ticket_query: str
    keyword_terms: list[str]
    rewrite_mode: str
    rewrite_version: str = "rag.query_rewrite.v1.0"
    warnings: list[str] = Field(default_factory=list)


class RetrievalCandidate(StrictModel):
    source_type: SourceType
    source_id: str
    chunk_id: str | None = None
    content_summary: str
    citation: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    keyword_score: float | None = Field(default=None, ge=0, le=1)
    vector_score: float | None = Field(default=None, ge=0, le=1)
    rerank_score: float | None = Field(default=None, ge=0, le=1)
    source_reliability: float = Field(default=0, ge=0, le=1)
    verification_score: float = Field(default=0, ge=0, le=1)
    freshness_score: float = Field(default=0.6, ge=0, le=1)
    relevance_to_alarm: float = Field(default=0, ge=0, le=1)
    retrieval_score: float = Field(default=0, ge=0, le=1)
    final_score: float = Field(default=0, ge=0, le=1)
    need_manual_confirmation: bool = False
    embedding: list[float] | None = Field(default=None, exclude=True)

    @property
    def identity(self) -> tuple[str, str, str]:
        return (self.source_type, self.source_id, self.chunk_id or "")


class RankedEvidence(RetrievalCandidate):
    package_id: str | None = None


class RetrievalMetadata(StrictModel):
    retrieval_mode: RetrievalMode
    keyword_candidate_count: int = 0
    vector_candidate_count: int = 0
    rerank_candidate_count: int = 0
    final_count: int = 0
    rerank_applied: bool = False
    partial_result: bool = False
    degraded_components: list[str] = Field(default_factory=list)
    index_generation: str | None = None


class RetrievalResult(StrictModel):
    query_rewrite: QueryRewrite
    ranked_evidence: list[RankedEvidence]
    retrieval_metadata: RetrievalMetadata


class EvidencePackage(StrictModel):
    package_id: str
    package_version: str = "rag.evidence.v1.0"
    query_rewrite: QueryRewrite
    device_filters: dict[str, Any]
    manual_evidence: list[RankedEvidence]
    ticket_evidence: list[RankedEvidence]
    timeseries_summary_ref: str | None = None
    candidate_counts: dict[str, int]
    degraded_components: list[str]
    warnings: list[str]
    created_at: datetime
