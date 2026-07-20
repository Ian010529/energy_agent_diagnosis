import json
from pathlib import Path

from energy_agent.evaluation.contracts import EvaluationSample, EvaluationSplit


def _jsonl(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_split(dataset_root: Path, split: EvaluationSplit) -> list[EvaluationSample]:
    runtime_rows = _jsonl(dataset_root / "evaluation" / split / "runtime.jsonl")
    gold_rows = _jsonl(dataset_root / "gold" / f"{split}.jsonl")
    gold_by_id = {str(row["sample_id"]): row for row in gold_rows}
    if len(runtime_rows) != len(gold_rows):
        raise ValueError(f"{split} runtime/Gold sample count mismatch")
    samples = [
        EvaluationSample(runtime=row, gold=gold_by_id[str(row["sample_id"])])
        for row in runtime_rows
    ]
    if len({sample.runtime.sample_id for sample in samples}) != len(samples):
        raise ValueError(f"{split} contains duplicate sample IDs")
    for sample in samples:
        if (
            sample.runtime.sample_id != sample.gold.sample_id
            or sample.runtime.split != sample.gold.split
            or sample.runtime.dataset_version != sample.gold.dataset_version
        ):
            raise ValueError(f"Evaluation pair mismatch: {sample.runtime.sample_id}")
    return samples
