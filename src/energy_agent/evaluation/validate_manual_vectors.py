import json
from pathlib import Path
from typing import Any

import numpy as np
from pymilvus import MilvusClient

from energy_agent.core.config import Settings

DATASET_ROOT = Path("artifacts/synthetic-data/pilot_medium_v1-1.3.0")


def _expected_chunks() -> dict[str, dict[str, Any]]:
    import gzip

    with gzip.open(
        DATASET_ROOT / "reports" / "manual_chunks_rebuilt.jsonl.gz",
        "rt",
        encoding="utf-8",
    ) as handle:
        rows = [json.loads(line) for line in handle]
    return {row["chunk_id"]: row for row in rows if row["effective"]}


def validate() -> dict[str, object]:
    settings = Settings()
    expected = _expected_chunks()
    client = MilvusClient(uri=settings.milvus_uri, token=settings.milvus_token or "")
    try:
        rows = client.query(
            settings.milvus_manual_collection,
            filter="",
            limit=10_000,
            output_fields=["id", "source_id", "index_generation", "embedding"],
        )
    finally:
        client.close()
    indexed = {str(row["id"]): row for row in rows}
    missing = sorted(set(expected) - set(indexed))
    unexpected = sorted(set(indexed) - set(expected))
    if missing or unexpected:
        raise ValueError(
            f"MANUAL_VECTOR_ID_MISMATCH:missing={len(missing)}:unexpected={len(unexpected)}"
        )
    ordered_ids = sorted(expected)
    vectors = np.asarray([indexed[chunk_id]["embedding"] for chunk_id in ordered_ids], dtype="f4")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    if np.any(norms == 0):
        raise ValueError("MANUAL_VECTOR_ZERO_NORM")
    vectors /= norms
    similarities = vectors @ vectors.T
    np.fill_diagonal(similarities, -1)
    nearest = similarities.max(axis=1)
    result: dict[str, object] = {
        "dataset_id": "pilot_medium_v1",
        "dataset_version": "1.3.0",
        "embedding_model": settings.embedding_model,
        "embedding_dimension": int(vectors.shape[1]),
        "effective_chunk_count": len(ordered_ids),
        "milvus_readback_count": len(indexed),
        "missing_chunk_count": len(missing),
        "unexpected_chunk_count": len(unexpected),
        "nearest_neighbor": {},
        "status": "EXECUTED",
    }
    nearest_metrics = result["nearest_neighbor"]
    assert isinstance(nearest_metrics, dict)
    for threshold in (0.90, 0.95, 0.98):
        count = int(np.count_nonzero(nearest > threshold))
        nearest_metrics[f"above_{threshold:.2f}"] = count
        nearest_metrics[f"rate_above_{threshold:.2f}"] = count / len(nearest)
    return result


def main() -> None:
    print(json.dumps(validate(), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
