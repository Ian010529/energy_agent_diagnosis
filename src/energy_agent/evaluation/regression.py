import json
from pathlib import Path


def compare_baseline(current: dict[str, object], baseline: dict[str, object]) -> dict[str, object]:
    keys = sorted(set(current) | set(baseline))
    changes: dict[str, object] = {}
    for key in keys:
        before = baseline.get(key)
        after = current.get(key)
        delta = (
            float(after) - float(before)
            if isinstance(before, int | float) and isinstance(after, int | float)
            else None
        )
        changes[key] = {"baseline": before, "current": after, "delta": delta}
    return changes


def accept_baseline(
    *,
    report_path: Path,
    baseline_path: Path,
    expected_dataset_version: str,
) -> None:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report["dataset"]["version"] != expected_dataset_version:
        raise ValueError("Dataset version differs from baseline target")
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(
        json.dumps(
            {
                "dataset": report["dataset"],
                "waiver_id": report["waiver_id"],
                "metrics": report["metrics"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
