from pathlib import Path

from energy_agent.evaluation.contracts import EvaluationSample, EvaluationSplit
from energy_agent.evaluation.loader import load_split

EXPECTED_SPLIT_COUNTS: dict[EvaluationSplit, int] = {
    "calibration": 100,
    "regression": 100,
    "holdout": 50,
}


def load_pilot_dataset(root: Path, split: EvaluationSplit) -> list[EvaluationSample]:
    samples = load_split(root, split)
    expected = EXPECTED_SPLIT_COUNTS[split]
    if len(samples) != expected:
        raise ValueError(f"{split} requires {expected} samples, found {len(samples)}")
    return samples
