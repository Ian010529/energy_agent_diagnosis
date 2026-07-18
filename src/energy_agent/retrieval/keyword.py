import re
from collections.abc import Iterable


def keyword_terms(query: str) -> set[str]:
    latin = re.findall(r"[A-Za-z0-9_-]+", query.lower())
    chinese = re.findall(r"[\u4e00-\u9fff]{2,}", query)
    terms = set(latin)
    for phrase in chinese:
        terms.add(phrase)
        terms.update(phrase[index : index + 2] for index in range(len(phrase) - 1))
    return terms


def relevance_score(query: str, text: str) -> float:
    terms = keyword_terms(query)
    if not terms:
        return 0.0
    normalized = text.lower()
    hits = sum(1 for term in terms if term in normalized)
    return round(hits / len(terms), 4)


def rank_rows(
    query: str, rows: Iterable[dict[str, object]], fields: tuple[str, ...], top_k: int
) -> list[dict[str, object]]:
    ranked = []
    for row in rows:
        text = " ".join(str(row.get(field) or "") for field in fields)
        score = relevance_score(query, text)
        if score > 0:
            ranked.append({**row, "keyword_score": score})
    return sorted(
        ranked,
        key=lambda item: (
            item["keyword_score"] if isinstance(item["keyword_score"], float | int) else 0.0
        ),
        reverse=True,
    )[:top_k]
