"""Run the Stage 3 RAG offline evaluation set and print JSON metrics."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from energy_agent_diagnosis.contracts import RequestContext, ToolContext
from energy_agent_diagnosis.core.config import ProviderSettings, RetrievalSettings
from energy_agent_diagnosis.providers import build_provider_registry
from energy_agent_diagnosis.retrieval import retrieve_evidence


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Evaluate Stage 3 RAG retrieval.")
    parser.add_argument(
        "--cases",
        default="tests/fixtures/rag_eval_cases.json",
        help="Path to evaluation cases JSON.",
    )
    parser.add_argument("--score-threshold", type=float, default=0.1)
    return parser.parse_args()


async def evaluate_case(case: dict[str, Any], settings: RetrievalSettings) -> dict[str, Any]:
    """Evaluate one RAG case against the local Mock/D2 retrieval baseline."""
    request = RequestContext.model_validate(
        {
            "request_id": f"eval-{case['case_id']}",
            "trace_id": f"trace-{case['case_id']}",
            "session_id": f"session-{case['case_id']}",
            "source": "offline_eval",
            "site": {"site_id": case.get("site_id")},
            "device": {
                "device_type": case.get("device_type"),
                "device_model": case.get("device_model"),
                "manufacturer": case.get("manufacturer"),
            },
            "alarm": {"alarm_name": case.get("alarm_name")},
            "message": case.get("message", ""),
        }
    )
    registry = build_provider_registry(ProviderSettings())
    package = await retrieve_evidence(
        registry,
        ToolContext(trace_id=request.trace_id, source_system="offline-eval"),
        request,
        settings,
    )
    source_types = {item.source_type for item in package.ranked_evidence}
    quotes = "\n".join(item.quote_text for item in package.ranked_evidence)
    expected_sources = set(case.get("expected_sources", []))
    expected_terms = list(case.get("expected_terms", []))
    missing_sources = sorted(expected_sources.difference(source_types))
    missing_terms = [term for term in expected_terms if term not in quotes]
    passed = not missing_sources and not missing_terms
    return {
        "case_id": case["case_id"],
        "passed": passed,
        "missing_sources": missing_sources,
        "missing_terms": missing_terms,
        "evidence_count": len(package.ranked_evidence),
        "degraded_sources": package.degraded_sources,
        "need_manual_confirmation": package.need_manual_confirmation,
    }


async def main_async(cases: list[Any], score_threshold: float) -> int:
    """Run retrieval cases, print aggregate metrics, and return status."""
    if not isinstance(cases, list):
        raise ValueError("RAG eval cases must be a JSON array")
    settings = RetrievalSettings(score_threshold=score_threshold)
    results = [await evaluate_case(case, settings) for case in cases if isinstance(case, dict)]
    passed = sum(1 for result in results if result["passed"])
    report = {
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "pass_rate": round(passed / len(results), 4) if results else 0.0,
        "results": results,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["failed"] == 0 else 1


def main() -> int:
    """CLI entrypoint."""
    args = parse_args()
    cases_path = Path(args.cases)
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    return asyncio.run(main_async(cases, args.score_threshold))


if __name__ == "__main__":
    raise SystemExit(main())
