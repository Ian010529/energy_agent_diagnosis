import math

from energy_agent.retrieval.contracts import RetrievalCandidate, SourceType


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    denominator = math.sqrt(sum(v * v for v in left)) * math.sqrt(sum(v * v for v in right))
    return sum(a * b for a, b in zip(left, right, strict=True)) / denominator if denominator else 0


def deduplicate_and_diversify(
    candidates: list[RetrievalCandidate],
    *,
    top_k: int,
    semantic_threshold: float = 0.92,
    max_chunks_per_document: int = 2,
    max_results_per_ticket: int = 1,
    minimum_quality: float = 0.45,
) -> list[RetrievalCandidate]:
    ordered = sorted(candidates, key=lambda item: item.final_score, reverse=True)
    selected: list[RetrievalCandidate] = []
    identities: set[tuple[str, str, str]] = set()
    counts: dict[tuple[str, str], int] = {}
    for candidate in ordered:
        if candidate.final_score < minimum_quality or candidate.identity in identities:
            continue
        limit = (
            max_chunks_per_document
            if candidate.source_type == SourceType.MANUAL
            else max_results_per_ticket
        )
        count_key = (candidate.source_type, candidate.source_id)
        if counts.get(count_key, 0) >= limit:
            continue
        if candidate.embedding and any(
            existing.embedding
            and cosine_similarity(candidate.embedding, existing.embedding) > semantic_threshold
            for existing in selected
        ):
            continue
        selected.append(candidate)
        identities.add(candidate.identity)
        counts[count_key] = counts.get(count_key, 0) + 1
        if len(selected) == top_k:
            break
    source_types = {item.source_type for item in selected}
    if len(source_types) == 1 and selected and len(selected) >= 2:
        alternate = next(
            (
                item
                for item in ordered
                if item.source_type not in source_types
                and item.final_score >= minimum_quality
                and item.identity not in identities
            ),
            None,
        )
        if alternate:
            selected[-1] = alternate
            selected.sort(key=lambda item: item.final_score, reverse=True)
    return selected
