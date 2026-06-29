"""阶段 3 证据包生成。"""

import hashlib
from typing import Any

from energy_agent_diagnosis.contracts import EvidenceItem, EvidencePackage

from .models import RetrievalCandidate


def build_evidence_package(
    *,
    session_id: str,
    trace_id: str,
    candidates: list[RetrievalCandidate],
    degraded_sources: tuple[str, ...],
    settings: Any,
) -> EvidencePackage:
    """把重排后的候选转换为公共标准证据包。"""
    max_quote_chars = int(_setting(settings, "max_quote_chars", 180))
    ranked = [
        _to_evidence_item(candidate, index, max_quote_chars)
        for index, candidate in enumerate(candidates, start=1)
    ]
    strong_count = sum(1 for item in ranked if not item.weak_evidence)
    min_strong = int(_setting(settings, "min_strong_evidence_count", 1))
    package_id = _stable_id("pkg", session_id, trace_id, *(item.evidence_id for item in ranked))
    return EvidencePackage(
        package_id=package_id,
        session_id=session_id,
        trace_id=trace_id,
        ranked_evidence=ranked,
        degraded_sources=list(degraded_sources),
        need_manual_confirmation=strong_count < min_strong or not ranked,
    )


def _to_evidence_item(
    candidate: RetrievalCandidate,
    index: int,
    max_quote_chars: int,
) -> EvidenceItem:
    evidence_id = _stable_id(
        "evd",
        candidate.source_type,
        candidate.source_id,
        str(candidate.raw.get("chunk_id", "")),
        str(index),
    )
    metadata = dict(candidate.metadata)
    metadata.update(
        {
            "final_score": candidate.final_score,
            "source_reliability": candidate.source_reliability,
            "raw": candidate.raw,
        }
    )
    return EvidenceItem(
        evidence_id=evidence_id,
        source_type=candidate.source_type,
        source_id=candidate.source_id,
        chunk_id=_optional_str(candidate.raw.get("chunk_id")),
        page_number=_optional_int(candidate.raw.get("page_no")),
        section=_optional_str(
            candidate.raw.get("chapter_title")
            or candidate.raw.get("component")
            or candidate.raw.get("alarm_name")
        ),
        quote_text=_clip(candidate.content, max_quote_chars),
        score=round(candidate.final_score, 4),
        verified=candidate.verified,
        weak_evidence=candidate.weak_evidence,
        metadata=metadata,
    )


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def _clip(value: str, max_chars: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= max_chars:
        return normalized
    return f"{normalized[: max_chars - 1]}…"


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _setting(settings: Any, name: str, default: Any) -> Any:
    value = getattr(settings, name, default)
    return default if value is None else value
