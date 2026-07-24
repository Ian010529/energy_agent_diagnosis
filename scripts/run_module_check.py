from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ModuleCheck:
    source_paths: tuple[str, ...]
    test_args: tuple[str, ...]


MODULES = {
    "agent": ModuleCheck(
        ("src/energy_agent/agent", "src/energy_agent/bootstrap/diagnosis_runtime.py"),
        (
            "tests/unit/test_graph.py",
            "tests/unit/test_state.py",
            "tests/unit/test_phase7_frontend_api.py::test_entity_parser_extracts_traceable_device_and_alarm_ids",
            "tests/unit/test_phase7_frontend_api.py::test_create_session_initial_run_is_not_marked_running",
            "tests/unit/test_phase7_frontend_api.py::test_create_session_idempotency_replay_precedes_alarm_dedup",
            "tests/unit/test_phase7_frontend_api.py::test_cancelled_stream_restores_retryable_session",
        ),
    ),
    "cases": ModuleCheck(
        ("src/energy_agent/cases",),
        ("tests/unit/test_phase4_human_cases.py",),
    ),
    "catalog": ModuleCheck(
        ("src/energy_agent/catalog",),
        (
            "tests/unit/test_phase7_frontend_api.py",
            "-k",
            "catalog or query_datetime or alarm_support",
        ),
    ),
    "evidence": ModuleCheck(
        ("src/energy_agent/evidence",),
        (
            "tests/unit/test_phase7_frontend_api.py",
            "-k",
            "evidence or timeseries",
        ),
    ),
    "graph": ModuleCheck(
        ("src/energy_agent/graph",),
        ("tests/unit/test_phase5_async_graph_scenarios.py", "-k", "graph"),
    ),
    "guardrails": ModuleCheck(
        ("src/energy_agent/guardrails",),
        ("tests/unit/test_phase6_hardening.py", "-k", "guardrail"),
    ),
    "indexing": ModuleCheck(
        ("src/energy_agent/indexing",),
        (
            "tests/unit/test_phase5_async_graph_scenarios.py::"
            "test_index_event_schema_status_idempotency_and_retry_decision",
        ),
    ),
    "memory": ModuleCheck(
        ("src/energy_agent/memory",),
        ("tests/unit/modules/test_memory.py",),
    ),
    "model": ModuleCheck(
        ("src/energy_agent/model",),
        (
            "tests/unit/test_phase6_hardening.py",
            "-k",
            "reasoning_effort or invalid_provider_response",
        ),
    ),
    "retrieval": ModuleCheck(
        ("src/energy_agent/retrieval",),
        ("tests/unit/test_phase3_rag.py",),
    ),
    "timeline": ModuleCheck(
        ("src/energy_agent/timeline",),
        ("tests/unit/test_phase7_frontend_api.py", "-k", "timeline"),
    ),
    "tools": ModuleCheck(
        ("src/energy_agent/tools",),
        ("tests/unit/test_phase2_core.py", "-k", "tool or timeseries"),
    ),
    "users": ModuleCheck(
        ("src/energy_agent/users",),
        (
            "tests/unit/test_phase7_5_auth.py",
            "tests/contract/test_phase7_5_auth_contracts.py",
        ),
    ),
}


def run(*command: str) -> None:
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode:
        raise SystemExit(result.returncode)


def main() -> int:
    if sys.argv[1:] == ["--list"]:
        print(" ".join(sorted(MODULES)))
        return 0
    if len(sys.argv) != 2 or sys.argv[1] not in MODULES:
        print("usage: run_module_check.py MODULE")
        print(f"modules: {', '.join(sorted(MODULES))}")
        return 2
    module = sys.argv[1]
    check = MODULES[module]
    test_paths = tuple(
        dict.fromkeys(
            argument.split("::", 1)[0]
            for argument in check.test_args
            if argument.startswith("tests/")
        )
    )
    run(sys.executable, "scripts/check_module_boundaries.py")
    run(sys.executable, "-m", "ruff", "check", *check.source_paths, *test_paths)
    run(sys.executable, "-m", "mypy", *check.source_paths)
    run(sys.executable, "-m", "pytest", *check.test_args)
    print(f"module check passed: {module}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
