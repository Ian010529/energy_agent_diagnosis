from dataclasses import dataclass
from datetime import UTC, datetime

from energy_agent.retrieval.contracts import RetrievalCandidate, SourceType


@dataclass(frozen=True)
class ScoreWeights:
    keyword: float = 0.30
    vector: float = 0.40
    rerank: float = 0.30
    final_retrieval: float = 0.35
    source_reliability: float = 0.20
    verification: float = 0.15
    relevance_to_alarm: float = 0.15
    freshness: float = 0.15


DEFAULT_SCORE_WEIGHTS = ScoreWeights()


def normalize_scores(values: list[float]) -> list[float]:
    if not values:
        return []
    low, high = min(values), max(values)
    if high == low:
        return [1.0 if high > 0 else 0.0 for _ in values]
    return [(value - low) / (high - low) for value in values]


def retrieval_score(
    keyword: float | None,
    vector: float | None,
    rerank: float | None,
    weights: ScoreWeights = DEFAULT_SCORE_WEIGHTS,
) -> float:
    channels = [
        (keyword, weights.keyword),
        (vector, weights.vector),
        (rerank, weights.rerank),
    ]
    available_weight = sum(weight for value, weight in channels if value is not None)
    if not available_weight:
        return 0.0
    return sum((value or 0.0) * weight for value, weight in channels) / available_weight


def final_score(
    retrieval: float,
    reliability: float,
    verification: float,
    relevance: float,
    freshness: float,
    weights: ScoreWeights = DEFAULT_SCORE_WEIGHTS,
) -> float:
    return (
        weights.final_retrieval * retrieval
        + weights.source_reliability * reliability
        + weights.verification * verification
        + weights.relevance_to_alarm * relevance
        + weights.freshness * freshness
    )


def source_reliability(source_type: SourceType, metadata: dict[str, object]) -> float:
    if source_type == SourceType.MANUAL:
        return 1.0 if metadata.get("source_class", "official_manual") == "official_manual" else 0.95
    if source_type == SourceType.CASE:
        return 0.95
    return 0.85 if metadata.get("verified") else 0.65


def verification_score(source_type: SourceType, metadata: dict[str, object]) -> float:
    if source_type == SourceType.MANUAL:
        return 1.0 if metadata.get("verified", True) else 0.30
    if metadata.get("verified") and metadata.get("closed", True):
        return 1.0
    return 0.70 if metadata.get("closed") else 0.30


def freshness_score(
    source_type: SourceType,
    timestamp: datetime | None,
    *,
    now: datetime | None = None,
    effective: bool = True,
) -> float:
    if source_type == SourceType.MANUAL:
        return 0.85 if effective else 0.50
    if timestamp is None:
        return 0.60
    current = now or datetime.now(UTC)
    value = timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=UTC)
    months = max(0, (current - value).days) / 30.44
    if months <= 3:
        return 1.0
    if months <= 6:
        return 0.85
    if months <= 12:
        return 0.70
    return 0.50


def alarm_relevance(candidate: RetrievalCandidate, filters: dict[str, object]) -> float:
    metadata = candidate.metadata
    anchors = ("alarm_name", "device_type", "device_model", "manufacturer", "component")
    applicable = [(filters.get(key), metadata.get(key)) for key in anchors if filters.get(key)]
    if any(actual and expected != actual for expected, actual in applicable[:3]):
        return 0.20
    matched = sum(expected == actual for expected, actual in applicable if actual)
    base = matched / len(applicable) if applicable else 0.50
    symptom_terms = filters.get("symptom_terms", [])
    if isinstance(symptom_terms, list) and symptom_terms:
        text = candidate.content_summary.lower()
        symptom = sum(str(term).lower() in text for term in symptom_terms) / len(symptom_terms)
        base = 0.75 * base + 0.25 * symptom
    return min(1.0, max(0.0, base))


def score_candidate(
    candidate: RetrievalCandidate,
    filters: dict[str, object],
    *,
    weights: ScoreWeights = DEFAULT_SCORE_WEIGHTS,
) -> RetrievalCandidate:
    reliability = source_reliability(candidate.source_type, candidate.metadata)
    verification = verification_score(candidate.source_type, candidate.metadata)
    close_time = candidate.metadata.get("close_time")
    timestamp = close_time if isinstance(close_time, datetime) else None
    freshness = freshness_score(
        candidate.source_type,
        timestamp,
        effective=bool(candidate.metadata.get("effective", True)),
    )
    relevance = alarm_relevance(candidate, filters)
    retrieval = retrieval_score(
        candidate.keyword_score, candidate.vector_score, candidate.rerank_score, weights
    )
    final = final_score(retrieval, reliability, verification, relevance, freshness, weights)
    return candidate.model_copy(
        update={
            "source_reliability": reliability,
            "verification_score": verification,
            "freshness_score": freshness,
            "relevance_to_alarm": relevance,
            "retrieval_score": retrieval,
            "final_score": final,
            "need_manual_confirmation": (
                candidate.source_type == SourceType.CASE or final < 0.65 or relevance <= 0.20
            ),
        }
    )
