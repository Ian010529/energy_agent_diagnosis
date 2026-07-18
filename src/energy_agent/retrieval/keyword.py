import math
from collections import Counter
from collections.abc import Sequence
from typing import cast

from energy_agent.retrieval.tokenization import tokenize


class LightweightKeywordRetriever:
    def rank(
        self,
        query: str,
        rows: Sequence[dict[str, object]],
        fields: Sequence[str],
        top_k: int,
        *,
        title_fields: Sequence[str] = (),
        exact_terms: Sequence[str] = (),
    ) -> list[dict[str, object]]:
        query_tokens = tokenize(query)
        if not query_tokens or not rows:
            return []
        documents = [
            tokenize(" ".join(str(row.get(field) or "") for field in fields)) for row in rows
        ]
        avg_len = sum(map(len, documents)) / len(documents) or 1
        doc_freq = Counter(token for doc in documents for token in set(doc))
        scored: list[tuple[float, dict[str, object]]] = []
        for row, tokens in zip(rows, documents, strict=True):
            counts = Counter(tokens)
            score = 0.0
            for term in query_tokens:
                frequency = counts[term]
                if not frequency:
                    continue
                idf = math.log(1 + (len(rows) - doc_freq[term] + 0.5) / (doc_freq[term] + 0.5))
                score += (
                    idf
                    * frequency
                    * 2.2
                    / (frequency + 1.2 * (0.25 + 0.75 * len(tokens) / avg_len))
                )
            title = " ".join(str(row.get(field) or "") for field in title_fields).lower()
            body = " ".join(str(row.get(field) or "") for field in fields).lower()
            score += sum(1.5 for term in exact_terms if term and term.lower() in title)
            score += sum(0.75 for term in exact_terms if term and term.lower() in body)
            if score > 0:
                scored.append((score, row))
        if not scored:
            return []
        maximum = max(score for score, _ in scored)
        ranked = [
            {**row, "keyword_raw_score": score, "keyword_score": score / maximum}
            for score, row in sorted(scored, key=lambda item: item[0], reverse=True)[:top_k]
        ]
        return ranked


def rank_rows(
    query: str,
    rows: list[dict[str, object]],
    fields: tuple[str, ...],
    top_k: int,
) -> list[dict[str, object]]:
    return LightweightKeywordRetriever().rank(query, rows, fields, top_k)


def relevance_score(query: str, text: str) -> float:
    """Backward-compatible lexical score for Phase 2 callers."""
    ranked = LightweightKeywordRetriever().rank(query, [{"text": text}], ("text",), 1)
    return float(cast(float, ranked[0]["keyword_score"])) if ranked else 0.0
