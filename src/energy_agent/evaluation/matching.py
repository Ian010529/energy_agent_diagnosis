import re
import unicodedata


def normalize_root_cause(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[\s，。；、,:：;（）()\\-_/]+", "", normalized)


def root_cause_matches(
    candidate: str, canonical_root_cause_id: str, accepted_aliases: list[str]
) -> bool:
    expected = {
        normalize_root_cause(canonical_root_cause_id),
        *(normalize_root_cause(alias) for alias in accepted_aliases),
    }
    return normalize_root_cause(candidate) in expected


def rank_hit(
    candidates: list[str],
    canonical_root_cause_id: str,
    accepted_aliases: list[str],
    top_k: int,
) -> bool:
    return any(
        root_cause_matches(item, canonical_root_cause_id, accepted_aliases)
        for item in candidates[:top_k]
    )
