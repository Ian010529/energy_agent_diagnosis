"""阶段 3 统一重排与分数融合。"""

import re
from typing import Any

from energy_agent_diagnosis.ports.retrieval_clients import call_reranker

from .models import RetrievalCandidate


async def rerank_candidates(
    candidates: list[RetrievalCandidate] | tuple[RetrievalCandidate, ...],
    settings: Any,
    client: Any = None,
    trace_id: str = "",
    query_text: str = "",
    degraded_sources: list[str] | None = None,
) -> list[RetrievalCandidate]:
    """对多来源候选做统一重排、去重和多样性控制。"""
    endpoint = getattr(settings, "reranker_endpoint", "")

    if endpoint and candidates:
        headers = {"x-trace-id": trace_id}
        pairs = [{"query": query_text, "text": cand.content} for cand in candidates]
        payload = {"pairs": pairs}
        try:
            data = await call_reranker(endpoint, payload, headers, client)
            if isinstance(data, list):
                scores = data
            elif isinstance(data, dict):
                scores = data.get("scores", [])
            else:
                scores = []

            if len(scores) == len(candidates):
                for cand, score in zip(candidates, scores, strict=True):
                    cand.rerank_score = float(score)
            else:
                if degraded_sources is not None:
                    degraded_sources.append("RERANKER_INVALID_RESPONSE")
                for cand in candidates:
                    cand.rerank_score = None
        except TimeoutError:
            if degraded_sources is not None:
                degraded_sources.append("RERANKER_TIMEOUT")
            for cand in candidates:
                cand.rerank_score = None
        except Exception as exc:
            # Check if HTTPStatusError / HTTPError / status_code exists on exception
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            reason = (
                f"RERANKER_HTTP_ERROR_{status_code}"
                if status_code
                else f"RERANKER_FAILED_{type(exc).__name__}"
            )
            if degraded_sources is not None:
                degraded_sources.append(reason)
            for cand in candidates:
                cand.rerank_score = None
    else:
        if not endpoint and candidates:
            if degraded_sources is not None:
                degraded_sources.append("RERANKER_NOT_CONFIGURED")
        for cand in candidates:
            cand.rerank_score = None

    candidates = _merge_duplicate_channels(list(candidates))

    query_alarm_name = ""
    query_device_model = ""
    for cand in candidates:
        cand_alarm = cand.metadata.get("alarm_name") or cand.raw.get("alarm_name")
        if cand_alarm and cand_alarm in query_text:
            query_alarm_name = cand_alarm
        cand_model = cand.metadata.get("device_model") or cand.raw.get("device_model")
        if cand_model and cand_model in query_text:
            query_device_model = cand_model

    if not query_alarm_name:
        for cand in candidates:
            val = cand.metadata.get("alarm_name") or cand.raw.get("alarm_name")
            if val:
                query_alarm_name = val
                break
    if not query_device_model:
        for cand in candidates:
            val = cand.metadata.get("device_model") or cand.raw.get("device_model")
            if val:
                query_device_model = val
                break

    scored = [
        _score_candidate(cand, settings, query_alarm_name, query_device_model)
        for cand in candidates
    ]
    deduped = _deduplicate(scored)

    dedup_limit = int(_setting(settings, "dedup_limit", 10))
    rerank_top_n = int(_setting(settings, "rerank_top_n", 30))
    final_top_k = int(_setting(settings, "final_top_k", 5))

    ordered = sorted(deduped, key=lambda item: item.final_score, reverse=True)[:rerank_top_n]
    diversified = _diversify(ordered, final_top_k)
    return diversified[:dedup_limit]


def _parse_freshness_score(date_str: str) -> float:
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", date_str.strip())
    if not match:
        return 0.60
    try:
        year = int(match.group(1))
        month = int(match.group(2))
        delta_months = (2026 - year) * 12 + (7 - month)
        if delta_months <= 3:
            return 1.00
        elif delta_months <= 6:
            return 0.85
        elif delta_months <= 12:
            return 0.70
        else:
            return 0.50
    except Exception:
        return 0.60


def _score_candidate(
    candidate: RetrievalCandidate,
    settings: Any,
    query_alarm_name: str = "",
    query_device_model: str = "",
) -> RetrievalCandidate:
    kw = candidate.keyword_score
    vec = candidate.vector_score
    rr = candidate.rerank_score

    if rr is not None:
        retrieval_score = 0.30 * (kw or 0.0) + 0.40 * (vec or 0.0) + 0.30 * rr
    else:
        if kw is not None and vec is not None:
            retrieval_score = 0.45 * kw + 0.55 * vec
        elif kw is not None:
            retrieval_score = kw
        elif vec is not None:
            retrieval_score = vec
        else:
            retrieval_score = 0.0

    if candidate.source_type == "manual":
        source_reliability = 1.00
    elif candidate.source_type == "ticket":
        source_reliability = 0.85 if candidate.verified else 0.65
    elif candidate.source_type == "graph":
        source_reliability = 0.60
    else:
        source_reliability = 0.40

    if candidate.verified:
        verification_score = 1.00
    elif candidate.weak_evidence:
        verification_score = 0.30
    else:
        verification_score = 0.70

    cand_alarm = candidate.metadata.get("alarm_name") or candidate.raw.get("alarm_name")
    cand_model = candidate.metadata.get("device_model") or candidate.raw.get("device_model")

    relevance = 0.50
    if query_alarm_name and cand_alarm:
        if query_alarm_name == cand_alarm:
            if query_device_model and cand_model and query_device_model == cand_model:
                relevance = 0.95
            else:
                relevance = 0.85
        elif query_alarm_name in cand_alarm or cand_alarm in query_alarm_name:
            relevance = 0.75
    elif not query_alarm_name:
        relevance = 0.60

    date_str = None
    for key in ("publish_time", "publish_date", "date"):
        val = candidate.metadata.get(key) or candidate.raw.get(key)
        if isinstance(val, str):
            date_str = val
            break
    if date_str:
        freshness_score = _parse_freshness_score(date_str)
    else:
        freshness_score = 0.60

    final_score = (
        0.35 * retrieval_score
        + 0.20 * source_reliability
        + 0.15 * verification_score
        + 0.15 * relevance
        + 0.15 * freshness_score
    )
    final_score = round(min(max(final_score, 0.0), 1.0), 4)

    candidate.retrieval_score = retrieval_score
    candidate.source_reliability = source_reliability
    candidate.verification_score = verification_score
    candidate.relevance_to_alarm = relevance
    candidate.freshness_score = freshness_score
    candidate.final_score = final_score

    # Populate metadata
    candidate.metadata["retrieval_score"] = retrieval_score
    candidate.metadata["source_reliability"] = source_reliability
    candidate.metadata["verification_score"] = verification_score
    candidate.metadata["relevance_to_alarm"] = relevance
    candidate.metadata["freshness_score"] = freshness_score
    candidate.metadata["final_score"] = final_score
    candidate.metadata["retrieval_channel"] = candidate.channel
    candidate.metadata["source_group"] = candidate.source_type
    candidate.metadata["raw_record_snapshot"] = candidate.raw

    return candidate


def _merge_duplicate_channels(
    candidates: list[RetrievalCandidate],
) -> list[RetrievalCandidate]:
    """归并同一证据的 keyword/vector 召回结果，保留多路分数用于融合。"""
    merged: dict[tuple[str, str], RetrievalCandidate] = {}
    for candidate in candidates:
        key = (candidate.source_type, _dedup_key(candidate))
        existing = merged.get(key)
        if existing is None:
            candidate.metadata["merged_channels"] = [candidate.channel]
            merged[key] = candidate
            continue

        keyword_score = _max_optional(existing.keyword_score, candidate.keyword_score)
        vector_score = _max_optional(existing.vector_score, candidate.vector_score)
        rerank_score = _max_optional(existing.rerank_score, candidate.rerank_score)

        if _base_score(candidate) > _base_score(existing):
            existing.content = candidate.content
            existing.raw = candidate.raw
            existing.source_id = candidate.source_id

        existing.keyword_score = keyword_score
        existing.vector_score = vector_score
        existing.rerank_score = rerank_score
        existing.verified = existing.verified or candidate.verified
        existing.weak_evidence = existing.weak_evidence and candidate.weak_evidence
        existing.channel = _merge_channel_name(existing.channel, candidate.channel)

        channels = existing.metadata.setdefault("merged_channels", [existing.channel])
        if isinstance(channels, list) and candidate.channel not in channels:
            channels.append(candidate.channel)
        existing.metadata.update(candidate.metadata)
        existing.metadata["merged_channels"] = channels
    return list(merged.values())


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


def _max_optional(left: float | None, right: float | None) -> float | None:
    values = [value for value in (left, right) if value is not None]
    return max(values) if values else None


def _base_score(candidate: RetrievalCandidate) -> float:
    return max(candidate.keyword_score or 0.0, candidate.vector_score or 0.0)


def _merge_channel_name(left: str, right: str) -> str:
    names = []
    for name in (*left.split("+"), *right.split("+")):
        if name and name not in names:
            names.append(name)
    return "+".join(names)


def _diversify(candidates: list[RetrievalCandidate], final_top_k: int) -> list[RetrievalCandidate]:
    """保留高分结果，同时避免手册/工单被单一来源挤出。"""
    selected: list[RetrievalCandidate] = []

    for source_type in ("manual", "ticket", "timeseries"):
        if len(selected) >= final_top_k:
            break
        best = next((item for item in candidates if item.source_type == source_type), None)
        if best is not None and best not in selected:
            selected.append(best)

    if not selected and candidates:
        selected.append(candidates[0])

    for candidate in candidates:
        if len(selected) >= final_top_k:
            break
        if candidate in selected:
            continue
        if candidate.source_type == "graph" and not any(
            item.source_type in {"manual", "ticket"} for item in selected
        ):
            continue
        selected.append(candidate)

    if len(selected) < final_top_k:
        for candidate in candidates:
            if candidate not in selected:
                selected.append(candidate)
            if len(selected) >= final_top_k:
                break
    if selected and selected[0].source_type == "graph":
        for index, candidate in enumerate(selected[1:], start=1):
            if candidate.source_type != "graph":
                selected[0], selected[index] = selected[index], selected[0]
                break
    return selected[:final_top_k]


def _setting(settings: Any, name: str, default: Any) -> Any:
    value = getattr(settings, name, default)
    return default if value is None else value
