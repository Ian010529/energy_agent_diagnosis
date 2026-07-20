import argparse
import asyncio
import hashlib
import json
import platform
from datetime import UTC, datetime
from pathlib import Path

from energy_agent.agent.templates.definitions import TEMPLATES
from energy_agent.core.config import Settings
from energy_agent.evaluation.dataset import load_pilot_dataset
from energy_agent.evaluation.metrics import compute_metrics
from energy_agent.evaluation.prepare import materialize_runtime_alarms
from energy_agent.evaluation.regression import accept_baseline, compare_baseline
from energy_agent.evaluation.report import write_report_artifacts
from energy_agent.evaluation.runner import PublicAPIEvaluationRunner
from energy_agent.evaluation.thresholds import TechnicalThresholds, evaluate_technical_gate

DATASET_VERSION = "1.3.0"
DATASET_ROOT = Path(f"artifacts/synthetic-data/pilot_medium_v1-{DATASET_VERSION}")
BGE_VALIDATION_PATH = Path(
    f"artifacts/pilot-readiness/data-{DATASET_VERSION}/real_bge_m3_validation.json"
)
EXTERNAL_READBACK_PATH = Path(
    f"artifacts/pilot-readiness/data-{DATASET_VERSION}/external_load_readback.json"
)
INDEX_GRAPH_READBACK_PATH = Path(
    f"artifacts/pilot-readiness/data-{DATASET_VERSION}/index_graph_readback.json"
)
WAIVER_ID: str | None = None


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_data_validation() -> tuple[dict[str, object], str]:
    bge_validation: dict[str, object] = (
        json.loads(BGE_VALIDATION_PATH.read_text(encoding="utf-8"))
        if BGE_VALIDATION_PATH.exists()
        else {"status": "NOT_EXECUTED"}
    )
    status = (
        "PASSED"
        if bge_validation.get("status") == "PASSED"
        and EXTERNAL_READBACK_PATH.exists()
        and INDEX_GRAPH_READBACK_PATH.exists()
        else "INCOMPLETE"
    )
    return bge_validation, status


async def _evaluate(args: argparse.Namespace) -> bool:
    settings = Settings()
    bge_validation, data_validation_status = _load_data_validation()
    samples = load_pilot_dataset(DATASET_ROOT, args.split)
    run_id = args.run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    if args.prepare_runtime:
        await materialize_runtime_alarms(settings.mysql_dsn, [sample.runtime for sample in samples])
    results = await PublicAPIEvaluationRunner(
        args.base_url,
        evaluation_run_id=run_id,
        internal_api_key=args.internal_api_key or settings.internal_api_key,
        concurrency=args.concurrency,
    ).run(samples)
    metrics = compute_metrics(samples, results)
    metrics["answerable_session_failure_rate"] = sum(
        item.phase == "FAILED" and sample.gold.expected_phase == "COMPLETED"
        for sample, item in zip(samples, results, strict=True)
    ) / len(results)
    gate = evaluate_technical_gate(metrics, TechnicalThresholds())
    process = await asyncio.create_subprocess_exec(
        "git",
        "rev-parse",
        "HEAD",
        stdout=asyncio.subprocess.PIPE,
    )
    stdout, _ = await process.communicate()
    if process.returncode:
        raise RuntimeError("Unable to resolve commit SHA")
    commit = stdout.decode().strip()
    recommendation = "CONDITIONAL_GO" if all(gate.values()) else "NO_GO"
    templates = [
        {"template_id": item.template_id, "template_version": item.template_version}
        for item in TEMPLATES
    ]
    known_limitations = []
    if bge_validation.get("status") != "PASSED":
        known_limitations.append(
            "Real BGE-M3 duplication validation must be rerun for dataset 1.3.0."
        )
    if settings.retrieval_mode != "hybrid":
        known_limitations.append("Hybrid vector retrieval was not enabled for this run.")
    if settings.rerank_mode == "disabled":
        known_limitations.append("External reranking was not enabled for this run.")
    if settings.model_mode == "disabled":
        known_limitations.append("External model generation was not enabled for this run.")
    if settings.observability_mode != "langfuse":
        known_limitations.append("Live LangFuse delivery was not validated by this run.")
    degradation_results = [
        {
            "profile": "observed_configuration",
            "status": "EXECUTED",
            "retrieval_mode": settings.retrieval_mode,
            "rerank_mode": settings.rerank_mode,
            "graph_mode": settings.graph_mode,
            "technical_gate": "PASSED" if all(gate.values()) else "FAILED",
        },
        *[
            {
                "profile": profile,
                "status": "NOT_EXECUTED",
                "reason": "Requires a separate controlled evaluation run.",
            }
            for profile in (
                "full_hybrid",
                "keyword_only",
                "hybrid_without_reranker",
                "graph_disabled",
            )
            if profile
            != (
                "full_hybrid"
                if settings.retrieval_mode == "hybrid"
                and settings.rerank_mode != "disabled"
                and settings.graph_mode == "neo4j"
                else "keyword_only"
                if settings.retrieval_mode == "keyword_only"
                else "hybrid_without_reranker"
                if settings.rerank_mode == "disabled"
                else "graph_disabled"
            )
        ],
    ]
    report: dict[str, object] = {
        "evaluation_run_id": run_id,
        "commit_sha": commit,
        "dataset": {
            "id": "pilot_medium_v1",
            "version": DATASET_VERSION,
            "manifest_sha256": _sha(DATASET_ROOT / "manifest.json"),
            "split": args.split,
        },
        "waiver_id": WAIVER_ID,
        "data_validation": {
            "status": data_validation_status,
            "real_bge_m3": bge_validation,
            "external_readback_path": str(EXTERNAL_READBACK_PATH),
            "index_graph_readback_path": str(INDEX_GRAPH_READBACK_PATH),
        },
        "metrics": metrics,
        "technical_gate_checks": gate,
        "technical_gate": "PASSED" if all(gate.values()) else "FAILED",
        "business_thresholds": "NOT_CONFIGURED",
        "recommendation": recommendation,
        "known_limitations": known_limitations,
        "degradation_results": degradation_results,
        "release_manifest": {
            "commit_sha": commit,
            "build_time": datetime.now(UTC).isoformat(),
            "application_version": "0.1.0",
            "python_version": platform.python_version(),
            "migration_head": "0006_phase6",
            "dataset_id": "pilot_medium_v1",
            "dataset_version": DATASET_VERSION,
            "waiver_id": WAIVER_ID,
            "data_validation_status": data_validation_status,
            "evaluation_run_id": run_id,
            "technical_gate": "PASSED" if all(gate.values()) else "FAILED",
            "business_thresholds": "NOT_CONFIGURED",
            "templates": templates,
            "prompt_versions": [
                "diag.clarification_generator.v1.0",
                "diag.reason_generator.v1.0",
                "diag.response_generator.v1.0",
            ],
            "rag_versions": {
                "query_rewrite": "rag.query_rewrite.v1.0",
                "evidence_package": "rag.evidence.v1.0",
            },
            "providers": {
                "model_mode": settings.model_mode,
                "model_name": settings.model_name,
                "embedding_mode": settings.embedding_mode,
                "embedding_model": settings.embedding_model,
                "rerank_mode": settings.rerank_mode,
                "rerank_model": settings.rerank_model,
                "retrieval_mode": settings.retrieval_mode,
                "query_rewrite_mode": settings.query_rewrite_mode,
                "graph_mode": settings.graph_mode,
                "observability_mode": settings.observability_mode,
            },
            "known_limitations": known_limitations,
        },
    }
    write_report_artifacts(
        output_dir=Path("artifacts/pilot-readiness") / run_id,
        report=report,
        results=results,
        config_fingerprint={
            "base_url": args.base_url,
            "split": args.split,
            "concurrency": args.concurrency,
            "dataset_manifest_sha256": _sha(DATASET_ROOT / "manifest.json"),
            "model_mode": settings.model_mode,
            "model_name": settings.model_name,
            "embedding_mode": settings.embedding_mode,
            "embedding_model": settings.embedding_model,
            "rerank_mode": settings.rerank_mode,
            "rerank_model": settings.rerank_model,
            "retrieval_mode": settings.retrieval_mode,
            "query_rewrite_mode": settings.query_rewrite_mode,
            "graph_mode": settings.graph_mode,
            "observability_mode": settings.observability_mode,
            "template_versions": templates,
        },
    )
    passed = all(gate.values())
    print(
        json.dumps(
            {
                "evaluation_run_id": run_id,
                "technical_gate": "PASSED" if passed else "FAILED",
                "recommendation": recommendation,
                "report": str(
                    Path("artifacts/pilot-readiness") / run_id / "evaluation_report.json"
                ),
            },
            ensure_ascii=False,
        )
    )
    return passed


def _evaluation_exit_code(passed: bool) -> int:
    return 0 if passed else 2


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument(
        "--split", choices=["calibration", "regression", "holdout"], required=True
    )
    evaluate.add_argument("--base-url", default="http://127.0.0.1:8000")
    evaluate.add_argument("--internal-api-key")
    evaluate.add_argument("--run-id")
    evaluate.add_argument("--prepare-runtime", action="store_true")
    evaluate.add_argument("--concurrency", type=int, default=1)
    baseline = subparsers.add_parser("accept-baseline")
    baseline.add_argument("--run-id", required=True)
    compare = subparsers.add_parser("compare")
    compare.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if args.command == "evaluate":
        raise SystemExit(_evaluation_exit_code(asyncio.run(_evaluate(args))))
    elif args.command == "accept-baseline":
        accept_baseline(
            report_path=Path("artifacts/pilot-readiness") / args.run_id / "evaluation_report.json",
            baseline_path=Path("evaluation/baselines/pilot_medium_v1.json"),
            expected_dataset_version=DATASET_VERSION,
        )
    else:
        report = json.loads(
            (Path("artifacts/pilot-readiness") / args.run_id / "evaluation_report.json").read_text(
                encoding="utf-8"
            )
        )
        baseline_data = json.loads(
            Path("evaluation/baselines/pilot_medium_v1.json").read_text(encoding="utf-8")
        )
        print(
            json.dumps(
                compare_baseline(report["metrics"], baseline_data["metrics"]),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
