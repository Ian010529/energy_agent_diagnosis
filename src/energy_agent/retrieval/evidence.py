import hashlib
import json
from datetime import UTC, datetime

from energy_agent.retrieval.contracts import (
    EvidencePackage,
    QueryRewrite,
    RankedEvidence,
    RetrievalCandidate,
    SourceType,
)


def build_evidence_package(
    rewrite: QueryRewrite,
    filters: dict[str, object],
    candidates: list[RetrievalCandidate],
    *,
    candidate_counts: dict[str, int],
    degraded_components: list[str],
    warnings: list[str],
    timeseries_summary_ref: str | None = None,
) -> EvidencePackage:
    identity = {
        "rewrite": rewrite.model_dump(mode="json"),
        "filters": filters,
        "evidence": [candidate.identity for candidate in candidates],
    }
    digest = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()[:24]
    package_id = f"evpkg_{digest}"
    ranked = [
        RankedEvidence.model_validate(
            {**candidate.model_dump(exclude={"embedding"}), "package_id": package_id}
        )
        for candidate in candidates
    ]
    return EvidencePackage(
        package_id=package_id,
        query_rewrite=rewrite,
        device_filters=filters,
        manual_evidence=[item for item in ranked if item.source_type == SourceType.MANUAL][:3],
        ticket_evidence=[item for item in ranked if item.source_type == SourceType.TICKET][:2],
        case_evidence=[item for item in ranked if item.source_type == SourceType.CASE][:3],
        timeseries_summary_ref=timeseries_summary_ref,
        candidate_counts=candidate_counts,
        degraded_components=sorted(set(degraded_components)),
        warnings=sorted(set(warnings)),
        created_at=datetime.now(UTC),
    )
