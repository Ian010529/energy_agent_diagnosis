from pathlib import Path

import pytest

from energy_agent.evaluation.dataset import load_pilot_dataset

pytestmark = pytest.mark.integration


def test_pilot_evaluation_pairs_runtime_and_gold_without_leakage() -> None:
    root = Path("artifacts/synthetic-data/pilot_medium_v1-1.3.0")
    for split, count in (("calibration", 100), ("regression", 100), ("holdout", 50)):
        samples = load_pilot_dataset(root, split)  # type: ignore[arg-type]
        assert len(samples) == count
        assert all(item.runtime.sample_id == item.gold.sample_id for item in samples)
