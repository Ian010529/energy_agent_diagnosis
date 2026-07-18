from collections.abc import Awaitable, Callable, Sequence
from typing import cast

from energy_agent.core.errors import (
    EmbeddingUnavailableError,
    MilvusUnavailableError,
    RerankerUnavailableError,
    RetrievalChannelsFailedError,
)
from energy_agent.observability.tracing import Tracer
from energy_agent.providers.embedding import OpenAICompatibleEmbeddingProvider
from energy_agent.providers.milvus import MilvusVectorProvider
from energy_agent.providers.mysql import MySQLDiagnosisProvider
from energy_agent.providers.reranker import HttpRerankerProvider
from energy_agent.retrieval.contracts import (
    QueryRewrite,
    RankedEvidence,
    RetrievalCandidate,
    RetrievalMetadata,
    RetrievalMode,
    RetrievalResult,
    SourceType,
)
from energy_agent.retrieval.dedup import deduplicate_and_diversify
from energy_agent.retrieval.evidence import build_evidence_package
from energy_agent.retrieval.keyword import LightweightKeywordRetriever
from energy_agent.retrieval.merge import merge_candidates
from energy_agent.retrieval.query_rewrite import rewrite_query
from energy_agent.retrieval.scoring import (
    DEFAULT_SCORE_WEIGHTS,
    ScoreWeights,
    score_candidate,
)


class RetrievalService:
    def __init__(
        self,
        *,
        mysql: MySQLDiagnosisProvider,
        tracer: Tracer,
        embedding: OpenAICompatibleEmbeddingProvider | None = None,
        milvus: MilvusVectorProvider | None = None,
        reranker: HttpRerankerProvider | None = None,
        query_rewrite_mode: str = "rules",
        default_mode: RetrievalMode = RetrievalMode.KEYWORD_ONLY,
        keyword_top_n: int = 20,
        vector_top_n: int = 20,
        rerank_input_size: int = 30,
        semantic_dedup_threshold: float = 0.92,
        max_chunks_per_document: int = 2,
        max_results_per_ticket: int = 1,
        weights: ScoreWeights = DEFAULT_SCORE_WEIGHTS,
        model_rewrite: Callable[[dict[str, object]], Awaitable[object]] | None = None,
    ) -> None:
        self.mysql = mysql
        self.tracer = tracer
        self.embedding = embedding
        self.milvus = milvus
        self.reranker = reranker
        self.query_rewrite_mode = query_rewrite_mode
        self.default_mode = default_mode
        self.keyword_top_n = keyword_top_n
        self.vector_top_n = vector_top_n
        self.rerank_input_size = rerank_input_size
        self.semantic_dedup_threshold = semantic_dedup_threshold
        self.max_chunks_per_document = max_chunks_per_document
        self.max_results_per_ticket = max_results_per_ticket
        self.weights = weights
        self.model_rewrite = model_rewrite
        self.keyword = LightweightKeywordRetriever()
        self._rewrites: dict[str, object] = {}
        self._rewrite_cache_limit = 1024

    async def search(
        self,
        source: SourceType,
        query: str,
        filters: dict[str, object],
        *,
        trace_id: str,
        mode: RetrievalMode | None = None,
        top_k: int = 5,
        score_threshold: float = 0.45,
        verified_only: bool = True,
    ) -> RetrievalResult:
        selected_mode = mode or self.default_mode
        rewrite_key = f"{trace_id}:{query}:{sorted(filters.items())}"
        with self.tracer.start_span(
            "retrieval.query_rewrite",
            trace_id=trace_id,
            metadata={
                "rewrite_version": "rag.query_rewrite.v1.0",
                "query_hash": __import__("hashlib").sha256(query.encode()).hexdigest(),
            },
        ):
            rewrite = self._rewrites.get(rewrite_key)
            if rewrite is None:
                rewrite = await rewrite_query(
                    query,
                    alarm_name=_string(filters.get("alarm_name")),
                    device_type=_string(filters.get("device_type")),
                    device_model=_string(filters.get("device_model")),
                    manufacturer=_string(filters.get("manufacturer")),
                    mode=self.query_rewrite_mode,
                    model_rewrite=self.model_rewrite,
                )
                if len(self._rewrites) >= self._rewrite_cache_limit:
                    self._rewrites.pop(next(iter(self._rewrites)))
                self._rewrites[rewrite_key] = rewrite
        typed_rewrite = QueryRewrite.model_validate(rewrite)
        if source == SourceType.MANUAL:
            rows = await self.mysql.manual_candidates(
                filters, strong_only=selected_mode != RetrievalMode.KEYWORD_ONLY
            )
        elif source == SourceType.TICKET:
            rows = await self.mysql.ticket_candidates(filters, verified_only=verified_only)
        else:
            case_candidates = getattr(self.mysql, "case_candidates", None)
            rows = (
                await case_candidates(
                    filters,
                    exclude_session_id=_string(filters.get("exclude_session_id")),
                )
                if case_candidates
                else []
            )
        keyword_candidates: list[RetrievalCandidate] = []
        vector_candidates: list[RetrievalCandidate] = []
        degraded = list(typed_rewrite.warnings)
        warnings = list(typed_rewrite.warnings)
        search_query = (
            typed_rewrite.manual_query
            if source == SourceType.MANUAL
            else typed_rewrite.ticket_query
        )
        if selected_mode != RetrievalMode.VECTOR_ONLY:
            with self.tracer.start_span(
                "retrieval.keyword_search",
                trace_id=trace_id,
                metadata={
                    "source": source,
                    "filters": filters,
                    "keyword_terms": typed_rewrite.keyword_terms,
                },
            ) as span:
                fields: tuple[str, ...] = (
                    ("alarm_name", "chapter_title", "summary_or_content")
                    if source == SourceType.MANUAL
                    else ("alarm_name", "fault_symptom", "root_cause", "action_taken")
                    if source == SourceType.TICKET
                    else (
                        "alarm_name",
                        "symptom_summary",
                        "timeseries_features",
                        "root_cause",
                        "embedding_text",
                    )
                )
                ranked = self.keyword.rank(
                    search_query,
                    rows,
                    fields,
                    self.keyword_top_n,
                    title_fields=("alarm_name", "chapter_title"),
                    exact_terms=typed_rewrite.keyword_terms,
                )
                keyword_candidates = [
                    _candidate(
                        source,
                        row,
                        keyword=float(cast(float, row["keyword_score"])),
                    )
                    for row in ranked
                ]
                span.set_output({"candidate_count": len(keyword_candidates)})
        if selected_mode != RetrievalMode.KEYWORD_ONLY:
            if not self.embedding or not self.milvus:
                degraded.extend(["embedding", "milvus"])
                warnings.append("EMBEDDING_UNAVAILABLE")
            else:
                try:
                    with self.tracer.start_span(
                        "retrieval.vector_search",
                        trace_id=trace_id,
                        metadata={"source": source, "allowed_id_count": len(rows)},
                    ) as span:
                        vector = (await self.embedding.embed([search_query]))[0]
                        id_field = (
                            "chunk_id"
                            if source == SourceType.MANUAL
                            else "ticket_id"
                            if source == SourceType.TICKET
                            else "case_id"
                        )
                        ids = [str(row[id_field]) for row in rows]
                        hits = await self.milvus.search(source, vector, ids, self.vector_top_n)
                        by_id = {str(row[id_field]): row for row in rows}
                        vector_candidates = [
                            _candidate(
                                source,
                                by_id[str(hit["id"])],
                                vector=float(cast(float, hit["vector_score"])),
                            ).model_copy(
                                update={
                                    "embedding": (
                                        list(cast(Sequence[float], hit["embedding"]))
                                        if hit.get("embedding") is not None
                                        else None
                                    )
                                }
                            )
                            for hit in hits
                            if str(hit["id"]) in by_id
                        ]
                        span.set_output({"candidate_count": len(vector_candidates)})
                except (EmbeddingUnavailableError, MilvusUnavailableError):
                    degraded.extend(["embedding", "milvus"])
                    warnings.append("VECTOR_SEARCH_FAILED")
        if (
            not keyword_candidates
            and not vector_candidates
            and (selected_mode == RetrievalMode.VECTOR_ONLY or not rows)
        ):
            if rows:
                raise RetrievalChannelsFailedError("All requested retrieval channels failed")
        merged = merge_candidates(
            keyword_candidates, vector_candidates, limit=self.rerank_input_size
        )
        rerank_applied = False
        if merged and selected_mode == RetrievalMode.HYBRID:
            if self.reranker:
                try:
                    with self.tracer.start_span(
                        "retrieval.rerank",
                        trace_id=trace_id,
                        metadata={
                            "candidate_ids": [_identity(item) for item in merged],
                            "candidate_count": len(merged),
                        },
                    ):
                        scores = await self.reranker.rerank(
                            search_query,
                            [(_identity(item), item.content_summary) for item in merged],
                        )
                    merged = [
                        item.model_copy(update={"rerank_score": scores[_identity(item)]})
                        for item in merged
                    ]
                    rerank_applied = True
                except RerankerUnavailableError:
                    degraded.append("reranker")
                    warnings.append("RERANKER_UNAVAILABLE")
            else:
                degraded.append("reranker")
                warnings.append("RERANKER_UNAVAILABLE")
        scored = [score_candidate(item, filters, weights=self.weights) for item in merged]
        final = deduplicate_and_diversify(
            scored,
            top_k=top_k,
            semantic_threshold=self.semantic_dedup_threshold,
            max_chunks_per_document=self.max_chunks_per_document,
            max_results_per_ticket=self.max_results_per_ticket,
            minimum_quality=score_threshold,
        )
        with self.tracer.start_span(
            "retrieval.evidence_aggregation",
            trace_id=trace_id,
            metadata={"source": source, "degraded_components": degraded},
        ) as span:
            package = build_evidence_package(
                typed_rewrite,
                filters,
                final,
                candidate_counts={
                    "keyword": len(keyword_candidates),
                    "vector": len(vector_candidates),
                    "rerank": len(merged) if rerank_applied else 0,
                    "final": len(final),
                },
                degraded_components=degraded,
                warnings=warnings,
            )
            ranked_evidence: Sequence[RankedEvidence] = (
                package.manual_evidence
                if source == SourceType.MANUAL
                else package.ticket_evidence
                if source == SourceType.TICKET
                else package.case_evidence
            )
            span.set_output(
                {
                    "package_id": package.package_id,
                    "evidence_ids": [_identity(item) for item in ranked_evidence],
                }
            )
        actual_mode = (
            RetrievalMode.HYBRID
            if keyword_candidates and vector_candidates
            else RetrievalMode.VECTOR_ONLY
            if vector_candidates
            else RetrievalMode.KEYWORD_ONLY
        )
        metadata = RetrievalMetadata(
            retrieval_mode=actual_mode,
            keyword_candidate_count=len(keyword_candidates),
            vector_candidate_count=len(vector_candidates),
            rerank_candidate_count=len(merged) if rerank_applied else 0,
            final_count=len(ranked_evidence),
            rerank_applied=rerank_applied,
            partial_result=bool(degraded),
            degraded_components=sorted(set(degraded)),
            index_generation=_index_generation(rows),
        )
        return RetrievalResult(
            query_rewrite=typed_rewrite,
            ranked_evidence=list(ranked_evidence),
            retrieval_metadata=metadata,
        )


def _string(value: object) -> str | None:
    return str(value) if value else None


def _identity(candidate: RetrievalCandidate) -> str:
    return ":".join(candidate.identity)


def _index_generation(rows: list[dict[str, object]]) -> str | None:
    generations = sorted(
        {str(row["index_generation"]) for row in rows if row.get("index_generation")}
    )
    return generations[-1] if generations else None


def _candidate(
    source: SourceType,
    row: dict[str, object],
    *,
    keyword: float | None = None,
    vector: float | None = None,
) -> RetrievalCandidate:
    if source == SourceType.MANUAL:
        source_id = str(row["doc_id"])
        chunk_id = str(row["chunk_id"])
        content = str(row["summary_or_content"])[:1200]
        citation = f"[手册: {source_id} {row.get('chapter_title')}/page={row.get('page_no')}]"
        metadata = {
            key: row.get(key)
            for key in (
                "device_type",
                "device_model",
                "manufacturer",
                "alarm_name",
                "version",
                "chapter_title",
                "section_type",
                "verified",
                "effective",
                "index_generation",
            )
        }
    elif source == SourceType.TICKET:
        source_id = str(row["ticket_id"])
        chunk_id = None
        content = (
            f"{row.get('fault_symptom', '')}；根因: {row.get('root_cause', '')}；"
            f"处理: {row.get('action_taken', '')}"
        )[:1200]
        citation = f"[工单: {source_id}]"
        metadata = {
            key: row.get(key)
            for key in (
                "device_type",
                "device_model",
                "manufacturer",
                "alarm_name",
                "site_id",
                "is_verified",
                "close_time",
                "index_generation",
            )
        }
        metadata["verified"] = row.get("is_verified")
        metadata["closed"] = bool(row.get("close_time"))
    else:
        source_id = str(row["case_id"])
        chunk_id = None
        steps = row.get("resolution_steps")
        step_text = "；".join(str(item) for item in steps) if isinstance(steps, list) else ""
        content = (
            f"{row.get('symptom_summary', '')}；时序: {row.get('timeseries_features', '')}；"
            f"根因: {row.get('root_cause', '')}；处理: {step_text}"
        )[:1200]
        citation = f"[案例: {source_id} v{row['case_version']}]"
        metadata = {
            key: row.get(key)
            for key in (
                "device_type",
                "device_model",
                "manufacturer",
                "alarm_name",
                "case_version",
                "review_status",
                "index_status",
                "is_active",
            )
        }
        metadata["verified"] = True
        metadata["closed"] = True
    return RetrievalCandidate(
        source_type=source,
        source_id=source_id,
        chunk_id=chunk_id,
        content_summary=content,
        citation=citation,
        metadata=metadata,
        keyword_score=keyword,
        vector_score=vector,
    )
