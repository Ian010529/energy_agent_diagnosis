import argparse
import asyncio
import math
from typing import cast

from energy_agent.core.config import Settings
from energy_agent.observability.langfuse import LangFuseTracer
from energy_agent.observability.tracing import LocalTracer, Tracer
from energy_agent.providers.embedding import OpenAICompatibleEmbeddingProvider
from energy_agent.providers.milvus import MilvusVectorProvider
from energy_agent.providers.reranker import HttpRerankerProvider
from energy_agent.retrieval.contracts import RetrievalCandidate, SourceType
from energy_agent.retrieval.evidence import build_evidence_package
from energy_agent.retrieval.keyword import LightweightKeywordRetriever
from energy_agent.retrieval.merge import merge_candidates
from energy_agent.retrieval.query_rewrite import rule_rewrite
from energy_agent.retrieval.scoring import score_candidate


def embedding_provider(settings: Settings) -> OpenAICompatibleEmbeddingProvider:
    return OpenAICompatibleEmbeddingProvider(
        base_url=settings.embedding_base_url or "",
        api_key=settings.embedding_api_key or "",
        model=settings.embedding_model,
        dimension=settings.embedding_dimension,
        timeout_seconds=settings.embedding_timeout_seconds,
        batch_size=settings.embedding_batch_size,
    )


def reranker_provider(settings: Settings) -> HttpRerankerProvider:
    return HttpRerankerProvider(
        base_url=settings.rerank_base_url or "",
        api_key=settings.rerank_api_key or "",
        model=settings.rerank_model,
        timeout_seconds=settings.rerank_timeout_seconds,
    )


async def smoke_embedding(settings: Settings) -> int:
    if not settings.embedding_api_key:
        print("EMBEDDING_LIVE_VALIDATION=BLOCKED_MISSING_CREDENTIALS")
        return 2
    provider = embedding_provider(settings)
    try:
        vectors = await provider.embed(["PCS 温度告警", "散热风扇检查"])
        valid = (
            len(vectors) == 2
            and all(len(vector) == 1024 for vector in vectors)
            and all(math.isfinite(value) for vector in vectors for value in vector)
        )
        print(
            "EMBEDDING_LIVE_VALIDATION="
            f"{'PASSED' if valid else 'FAILED'} model={settings.embedding_model} "
            f"count={len(vectors)} dimension={len(vectors[0]) if vectors else 0}"
        )
        return 0 if valid else 1
    finally:
        await provider.close()


async def smoke_reranker(settings: Settings) -> int:
    if not settings.rerank_api_key:
        print("RERANKER_LIVE_VALIDATION=BLOCKED_MISSING_CREDENTIALS")
        return 2
    provider = reranker_provider(settings)
    try:
        scores = await provider.rerank(
            "PCS 温度告警如何排查",
            [
                ("relevant", "检查散热风扇、滤网和风道是否异常。"),
                ("irrelevant", "检查通信网络地址配置。"),
            ],
        )
        valid = set(scores) == {"relevant", "irrelevant"} and (
            scores["relevant"] > scores["irrelevant"]
        )
        print(
            "RERANKER_LIVE_VALIDATION="
            f"{'PASSED' if valid else 'FAILED'} model={settings.rerank_model} "
            f"aligned={set(scores) == {'relevant', 'irrelevant'}}"
        )
        return 0 if valid else 1
    finally:
        await provider.close()


async def smoke_rag(settings: Settings, tracer: Tracer) -> int:
    embedding = embedding_provider(settings)
    reranker = reranker_provider(settings)
    milvus = MilvusVectorProvider(
        uri=settings.milvus_uri,
        token=settings.milvus_token,
        manual_collection=settings.milvus_manual_collection,
        ticket_collection=settings.milvus_ticket_collection,
        dimension=settings.milvus_vector_dimension,
        metric_type=settings.milvus_metric_type,
    )
    ids = ["SMOKE-MANUAL-1", "SMOKE-MANUAL-2"]
    texts = [
        "PCS 温度告警时检查散热风扇、滤网和风道。",
        "PCS 通信异常时检查网络地址和交换机。",
    ]
    try:
        await milvus.ensure_collections()
        rewrite = rule_rewrite(
            "PCS 温度高如何排查",
            alarm_name="温度告警",
            device_type="PCS",
            device_model="SC5000",
        )
        vectors = await embedding.embed([*texts, rewrite.manual_query])
        await milvus.upsert(
            "manual",
            [
                {
                    "id": identifier,
                    "source_id": identifier,
                    "device_type": "PCS",
                    "device_model": "SC5000",
                    "manufacturer": "EnergyCo",
                    "alarm_name": "温度告警",
                    "index_generation": "smoke-v1",
                    "verified": True,
                    "effective": True,
                    "embedding": vector,
                }
                for identifier, vector in zip(ids, vectors[:2], strict=True)
            ],
        )
        rows: list[dict[str, object]] = [
            {
                "chunk_id": identifier,
                "doc_id": identifier,
                "alarm_name": "温度告警",
                "chapter_title": "散热维护",
                "summary_or_content": text,
            }
            for identifier, text in zip(ids, texts, strict=True)
        ]
        lexical = LightweightKeywordRetriever().rank(
            rewrite.manual_query,
            rows,
            ("alarm_name", "chapter_title", "summary_or_content"),
            2,
            exact_terms=rewrite.keyword_terms,
        )
        keyword = [
            RetrievalCandidate(
                source_type=SourceType.MANUAL,
                source_id=str(row["doc_id"]),
                chunk_id=str(row["chunk_id"]),
                content_summary=str(row["summary_or_content"]),
                citation=f"[手册: {row['doc_id']}]",
                metadata={
                    "verified": True,
                    "effective": True,
                    "alarm_name": "温度告警",
                    "device_type": "PCS",
                    "device_model": "SC5000",
                },
                keyword_score=float(cast(float, row["keyword_score"])),
                embedding=vectors[index],
            )
            for index, row in enumerate(lexical)
        ]
        hits = await milvus.search("manual", vectors[-1], ids, 2)
        by_id = {candidate.chunk_id: candidate for candidate in keyword}
        vector_candidates = [
            by_id[str(hit["id"])].model_copy(
                update={"vector_score": float(cast(float, hit["vector_score"]))}
            )
            for hit in hits
            if str(hit["id"]) in by_id
        ]
        merged = merge_candidates(keyword, vector_candidates)
        rerank_scores = await reranker.rerank(
            rewrite.manual_query,
            [(candidate.chunk_id or "", candidate.content_summary) for candidate in merged],
        )
        filters: dict[str, object] = {
            "alarm_name": "温度告警",
            "device_type": "PCS",
            "device_model": "SC5000",
        }
        ranked = sorted(
            [
                score_candidate(
                    candidate.model_copy(
                        update={"rerank_score": rerank_scores[candidate.chunk_id or ""]}
                    ),
                    filters,
                )
                for candidate in merged
            ],
            key=lambda candidate: candidate.final_score,
            reverse=True,
        )
        package = build_evidence_package(
            rewrite,
            filters,
            ranked[:2],
            candidate_counts={
                "keyword": len(keyword),
                "vector": len(vector_candidates),
                "rerank": len(merged),
                "final": min(2, len(ranked)),
            },
            degraded_components=[],
            warnings=[],
        )
        valid = (
            bool(package.manual_evidence)
            and package.manual_evidence[0].source_id == "SMOKE-MANUAL-1"
            and not package.degraded_components
        )
        print(
            "RAG_LIVE_VALIDATION="
            f"{'PASSED' if valid else 'FAILED'} package_id={package.package_id} "
            f"keyword={len(keyword)} vector={len(vector_candidates)} "
            f"rerank={len(merged)} final={len(package.manual_evidence)}"
        )
        return 0 if valid else 1
    finally:
        await milvus.delete("manual", ids)
        await embedding.close()
        await reranker.close()
        await milvus.close()
        await tracer.flush()
        await tracer.shutdown()


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("embedding", "reranker", "rag", "langfuse-rag"))
    args = parser.parse_args()
    settings = Settings()
    if args.kind == "embedding":
        return await smoke_embedding(settings)
    if args.kind == "reranker":
        return await smoke_reranker(settings)
    if args.kind == "langfuse-rag":
        if not settings.langfuse_public_key or not settings.langfuse_secret_key:
            print("LANGFUSE_RAG_VALIDATION=BLOCKED_MISSING_CREDENTIALS")
            return 2
        tracer: Tracer = LangFuseTracer(
            public_key=settings.langfuse_public_key or "",
            secret_key=settings.langfuse_secret_key or "",
            host=settings.langfuse_host,
            environment=settings.app_env,
        )
        if not await asyncio.to_thread(tracer.client.auth_check):  # type: ignore[attr-defined]
            print("LANGFUSE_RAG_VALIDATION=FAILED_AUTH")
            await tracer.shutdown()
            return 1
    else:
        tracer = LocalTracer()
    result = await smoke_rag(settings, tracer)
    if args.kind == "langfuse-rag" and result == 0:
        print("LANGFUSE_RAG_VALIDATION=PASSED")
    return result


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
