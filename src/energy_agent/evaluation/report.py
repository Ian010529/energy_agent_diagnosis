import json
from pathlib import Path
from typing import cast

from energy_agent.evaluation.contracts import PerSampleResult


def write_report_artifacts(
    *,
    output_dir: Path,
    report: dict[str, object],
    results: list[PerSampleResult],
    config_fingerprint: dict[str, object],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=False)
    gate_checks = cast(dict[str, bool], report["technical_gate_checks"])
    metrics = cast(dict[str, object], report["metrics"])
    known_limitations = cast(list[str], report.get("known_limitations", []))
    waiver_id = report.get("waiver_id")
    data_validation = cast(dict[str, object], report.get("data_validation", {}))
    (output_dir / "evaluation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md = [
        "# Pilot evaluation report",
        "",
        f"- Evaluation run: `{report['evaluation_run_id']}`",
        f"- Dataset: `{report['dataset']}`",
        f"- Waiver: `{waiver_id or 'none'}`",
        f"- Technical gate: `{report['technical_gate']}`",
        f"- Business thresholds: `{report['business_thresholds']}`",
        f"- Recommendation: `{report['recommendation']}`",
        "",
        "## Technical gates",
        "",
        "| Check | Passed |",
        "| --- | --- |",
        *[f"| {name} | {'yes' if passed else 'no'} |" for name, passed in gate_checks.items()],
        "",
        "## Key metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        *[
            f"| {name} | {value} |"
            for name, value in metrics.items()
            if name
            in {
                "sample_count",
                "top1",
                "top3",
                "tool_success_rate",
                "full_diagnosis_p95_seconds",
                "first_event_p95_seconds",
                "session_failure_rate",
                "gold_leak_count",
                "invalid_evidence_reference_count",
                "unsupported_strong_claim_count",
            }
        ],
        "",
        "## Known limitations",
        "",
        *[f"- {item}" for item in known_limitations],
    ]
    if waiver_id:
        md.extend(
            [
                "",
                "The manual-duplication technical validation remains failed and is accepted only",
                "for Phase 6 synthetic development under the recorded owner waiver.",
            ]
        )
    (output_dir / "evaluation_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    with (output_dir / "per_sample_results.jsonl").open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(result.model_dump_json() + "\n")
    failures = []
    for item in results:
        invalid_refs = [
            ref
            for refs in item.candidate_evidence_refs
            for ref in refs
            if ref not in set(item.evidence_ids)
        ]
        reasons = [
            reason
            for reason, active in (
                ("SESSION_FAILED", item.phase == "FAILED"),
                ("NO_CANDIDATE", not item.candidate_causes),
                ("GOLD_LEAK", item.gold_leak_detected),
                ("PROMPT_INJECTION_ESCAPED", item.prompt_injection_escaped),
                ("FORBIDDEN_ASSERTION", item.forbidden_assertion_count > 0),
                ("INVALID_EVIDENCE_REFERENCE", bool(invalid_refs)),
            )
            if active
        ]
        if reasons:
            row = item.model_dump(mode="json")
            row["failure_reasons"] = reasons
            row["invalid_evidence_refs"] = invalid_refs
            failures.append(row)
    (output_dir / "failure_examples.json").write_text(
        json.dumps(failures, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "degradation_results.json").write_text(
        json.dumps(
            report.get("degradation_results", []),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "data_validation_disclosure.json").write_text(
        json.dumps(
            {
                "waiver_id": waiver_id,
                "technical_validation": (
                    "FAILED_DUPLICATION_THRESHOLD"
                    if waiver_id
                    else data_validation.get("status", "INCOMPLETE")
                ),
                "governance_decision": (
                    "ACCEPTED_WITH_WAIVER" if waiver_id else "NO_ACTIVE_WAIVER"
                ),
                "real_bge_m3": data_validation.get("real_bge_m3"),
                "external_readback_path": data_validation.get("external_readback_path"),
                "index_graph_readback_path": data_validation.get("index_graph_readback_path"),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "release_manifest.json").write_text(
        json.dumps(report["release_manifest"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "config_fingerprint.json").write_text(
        json.dumps(config_fingerprint, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
