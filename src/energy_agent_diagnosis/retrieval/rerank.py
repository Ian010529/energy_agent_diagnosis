"""阶段 3 统一重排与分数融合。"""

from typing import Any

from .models import RetrievalCandidate


def rerank_candidates(
    candidates: list[RetrievalCandidate] | tuple[RetrievalCandidate, ...],
    settings: Any,
) -> list[RetrievalCandidate]:
    """对多来源候选做确定性 fallback 重排、去重和多样性控制。"""
    scored = [_score_candidate(candidate, settings) for candidate in candidates]
    deduped = _deduplicate(scored)
    rerank_top_n = int(_setting(settings, "rerank_top_n", 30))
    final_top_k = int(_setting(settings, "final_top_k", 5))
    ordered = sorted(deduped, key=lambda item: item.final_score, reverse=True)[:rerank_top_n]
    return _diversify(ordered, final_top_k)


def _score_candidate(candidate: RetrievalCandidate, settings: Any) -> RetrievalCandidate:
    source_weight = {
        "manual": float(_setting(settings, "manual_source_weight", 0.95)),
        "ticket": float(_setting(settings, "ticket_source_weight", 0.9)),
        "graph": float(_setting(settings, "graph_source_weight", 0.65)),
    }.get(candidate.source_type, 0.5)
    base_score = max(candidate.keyword_score or 0.0, candidate.vector_score or 0.0)
    if candidate.keyword_score is not None and candidate.vector_score is not None:
        base_score = (candidate.keyword_score * 0.45) + (candidate.vector_score * 0.55)
    score = base_score * source_weight
    if candidate.weak_evidence:
        score *= float(_setting(settings, "weak_evidence_penalty", 0.7))
    if candidate.verified:
        score += float(_setting(settings, "verified_evidence_boost", 0.08))
    candidate.source_reliability = source_weight
    candidate.rerank_score = round(min(max(score, 0.0), 1.0), 4)
    candidate.final_score = candidate.rerank_score
    return candidate


def _deduplicate(candidates: list[RetrievalCandidate]) -> list[RetrievalCandidate]:
    best_by_key: dict[tuple[str, str], RetrievalCandidate] = {}
    for candidate in candidates:
        key = (candidate.source_type, _dedup_key(candidate))
        existing = best_by_key.get(key)
        if existing is None or candidate.final_score > existing.final_score:
            best_by_key[key] = candidate
    return list(best_by_key.values())


def _dedup_key(candidate: RetrievalCandidate) -> str:
    if candidate.source_type == "manual":
        return str(candidate.raw.get("chunk_id") or candidate.source_id)
    if candidate.source_type == "ticket":
        return candidate.source_id
    if candidate.source_type == "graph":
        return "|".join(
            str(candidate.raw.get(field, ""))
            for field in ("alarm_name", "component", "fault_cause", "action")
        )
    return candidate.content[:80]


def _diversify(candidates: list[RetrievalCandidate], final_top_k: int) -> list[RetrievalCandidate]:
    selected: list[RetrievalCandidate] = []
    source_counts: dict[str, int] = {}
    for candidate in candidates:
        if len(selected) >= final_top_k:
            break
        count = source_counts.get(candidate.source_type, 0)
        if count >= max(2, final_top_k - 1) and any(
            item.source_type != candidate.source_type for item in candidates
        ):
            continue
        selected.append(candidate)
        source_counts[candidate.source_type] = count + 1
    if len(selected) < final_top_k:
        for candidate in candidates:
            if candidate not in selected:
                selected.append(candidate)
            if len(selected) >= final_top_k:
                break
    return selected


def _setting(settings: Any, name: str, default: Any) -> Any:
    value = getattr(settings, name, default)
    return default if value is None else value
