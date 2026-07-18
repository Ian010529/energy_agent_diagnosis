from energy_agent.retrieval.contracts import RetrievalCandidate
from energy_agent.retrieval.scoring import normalize_scores


def merge_candidates(
    keyword: list[RetrievalCandidate],
    vector: list[RetrievalCandidate],
    *,
    limit: int = 30,
) -> list[RetrievalCandidate]:
    keyword_normalized = normalize_scores([candidate.keyword_score or 0 for candidate in keyword])
    vector_normalized = normalize_scores([candidate.vector_score or 0 for candidate in vector])
    merged: dict[tuple[str, str, str], RetrievalCandidate] = {}
    for candidate, score in zip(keyword, keyword_normalized, strict=True):
        merged[candidate.identity] = candidate.model_copy(update={"keyword_score": score})
    for candidate, score in zip(vector, vector_normalized, strict=True):
        normalized = candidate.model_copy(update={"vector_score": score})
        existing = merged.get(candidate.identity)
        merged[candidate.identity] = (
            existing.model_copy(
                update={
                    "vector_score": normalized.vector_score,
                    "embedding": normalized.embedding or existing.embedding,
                }
            )
            if existing
            else normalized
        )
    return list(merged.values())[:limit]
