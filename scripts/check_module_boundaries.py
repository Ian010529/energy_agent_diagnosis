from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "energy_agent"


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    rule: str
    detail: str


# These are independent composition roots, not application modules. Each entry is
# intentionally explicit so a new file cannot silently inherit an exemption.
CONCRETE_PROVIDER_EXCEPTIONS = {
    "graph/bootstrap.py": "graph bootstrap CLI composition root",
    "indexing/worker.py": "index-worker process composition root",
    "retrieval/ingestion/cli.py": "document ingestion CLI composition root",
    "retrieval/ingestion/index_tickets.py": "ticket indexing CLI composition root",
    "retrieval/smoke.py": "provider smoke-test composition root",
}

SERVICE_FILES = {
    "agent/service.py",
    "agent/session_service.py",
    "agent/execution_service.py",
    "agent/persistence_coordinator.py",
    "cases/service.py",
    "cases/diagnosis_review.py",
    "cases/lifecycle.py",
    "cases/indexing.py",
    "catalog/service.py",
    "timeline/service.py",
    "evidence/service.py",
    "retrieval/service.py",
    "graph/service.py",
}

# Application services may depend on module-owned Protocols, never concrete
# persistence adapters. Infrastructure-oriented repositories/handlers are not
# included here because they are adapter implementations, not application code.
APPLICATION_SERVICE_FILES = SERVICE_FILES | {
    "cases/application.py",
    "cases/review_recorder.py",
    "indexing/publisher.py",
    "indexing/service.py",
    "retrieval/ingestion/service.py",
}


def imported_modules(tree: ast.AST) -> list[tuple[int, str]]:
    imports: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend((node.lineno, item.name) for item in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append((node.lineno, node.module))
    return imports


def is_client_component(path: Path) -> bool:
    try:
        first = path.read_text(encoding="utf-8").lstrip().splitlines()[0]
    except (IndexError, UnicodeDecodeError):
        return False
    return first.strip().rstrip(";") in {"'use client'", '"use client"'}


def check_python(path: Path) -> list[Violation]:
    relative = path.relative_to(SRC).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports = imported_modules(tree)
    violations: list[Violation] = []

    def add(line: int, rule: str, detail: str) -> None:
        violations.append(Violation(path.relative_to(ROOT), line, rule, detail))

    for line, module in imports:
        if relative.startswith("core/") and module.startswith(
            ("energy_agent.api", "energy_agent.providers", "energy_agent.persistence")
        ):
            add(line, "core-inward-only", module)
        if relative.startswith("contracts/") and module.startswith(
            (
                "energy_agent.agent",
                "energy_agent.api",
                "energy_agent.providers",
                "energy_agent.persistence",
            )
        ):
            add(line, "contracts-inward-only", module)
        if relative in SERVICE_FILES and module.startswith(("fastapi", "starlette")):
            add(line, "services-framework-free", module)
        if relative in APPLICATION_SERVICE_FILES and module.startswith("energy_agent.persistence"):
            add(line, "application-no-persistence-adapters", module)
        if relative == "evidence/service.py" and module.startswith(
            ("sqlalchemy", "energy_agent.persistence.models")
        ):
            add(line, "evidence-no-orm", module)
        if relative.startswith("api/") and module.startswith(
            ("energy_agent.persistence.models", "energy_agent.providers")
        ):
            add(line, "api-no-infrastructure", module)
        if relative.startswith(("providers/", "persistence/")) and module.startswith(
            "energy_agent.api"
        ):
            add(line, "infrastructure-no-api", module)
        if not relative.startswith("evaluation/") and module.startswith("energy_agent.evaluation"):
            add(line, "runtime-no-evaluation", module)
        if not relative.startswith("agent/") and module.startswith("energy_agent.agent.templates"):
            add(line, "template-ownership", module)
        if module.startswith("energy_agent.providers") and not (
            relative.startswith("bootstrap/")
            or relative.startswith("evaluation/")
            or relative in CONCRETE_PROVIDER_EXCEPTIONS
        ):
            add(line, "provider-composition-roots-only", module)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        if node.attr == "provider" and relative != "graph/service.py":
            add(node.lineno, "graph-provider-encapsulation", ".provider access")
        if (
            isinstance(node.value, ast.Attribute)
            and node.value.attr == "state"
            and node.attr != "container"
        ):
            add(node.lineno, "app-state-container-only", f"app.state.{node.attr}")
    return violations


def main() -> int:
    violations: list[Violation] = []
    for path in sorted(SRC.rglob("*.py")):
        violations.extend(check_python(path))
    frontend = ROOT / "frontend"
    for path in sorted(frontend.rglob("*.ts*")):
        if not path.is_file():
            continue
        if any(part in {"node_modules", ".next"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8")
        if is_client_component(path) and "BACKEND_INTERNAL_API_KEY" in text:
            violations.append(
                Violation(
                    path.relative_to(ROOT),
                    text[: text.index("BACKEND_INTERNAL_API_KEY")].count("\n") + 1,
                    "client-no-internal-key",
                    "BACKEND_INTERNAL_API_KEY",
                )
            )
    if violations:
        for item in violations:
            print(f"{item.path}:{item.line}: {item.rule}: {item.detail}")
        print(f"module boundary check failed: {len(violations)} violation(s)")
        return 1
    print("module boundary check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
