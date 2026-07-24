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

# Application services may depend on module-owned Protocols, never concrete
# persistence adapters. Infrastructure-oriented repositories/handlers are not
# included here because they are adapter implementations, not application code.
ADDITIONAL_APPLICATION_FILES = {
    "agent/persistence_coordinator.py",
    "cases/diagnosis_review.py",
    "cases/lifecycle.py",
    "cases/indexing.py",
    "cases/application.py",
    "cases/review_recorder.py",
    "indexing/publisher.py",
}

LOGICAL_MODULES = {
    "agent",
    "cases",
    "catalog",
    "evidence",
    "graph",
    "guardrails",
    "indexing",
    "memory",
    "model",
    "retrieval",
    "timeline",
    "tools",
    "users",
}

APPLICATION_GRAPH_EXCLUSIONS = {
    "graph/bootstrap.py",
    "indexing/worker.py",
    "retrieval/ingestion/cli.py",
    "retrieval/ingestion/index_tickets.py",
    "retrieval/smoke.py",
}


def is_application_service(relative: str) -> bool:
    return (
        relative.endswith("/service.py")
        or relative.endswith("_service.py")
        or relative in ADDITIONAL_APPLICATION_FILES
    )


def is_application_graph_file(relative: str) -> bool:
    if relative in APPLICATION_GRAPH_EXCLUSIONS:
        return False
    parts = relative.split("/")
    if parts[0] not in LOGICAL_MODULES:
        return False
    if any(part in {"implementations", "ingestion"} for part in parts[1:-1]):
        return False
    filename = parts[-1]
    return filename not in {
        "bootstrap.py",
        "cli.py",
        "gateway.py",
        "repository.py",
        "session_store.py",
        "smoke.py",
        "worker.py",
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
        if is_application_service(relative) and module.startswith(("fastapi", "starlette")):
            add(line, "services-framework-free", module)
        if is_application_service(relative) and module.startswith(
            ("energy_agent.persistence", "energy_agent.providers", "sqlalchemy")
        ):
            add(line, "application-no-persistence-adapters", module)
        if is_application_service(relative):
            owner = relative.split("/", 1)[0]
            if module.startswith(f"energy_agent.{owner}.repository"):
                add(line, "application-depends-on-port", module)
        if relative.startswith("agent/") and module.startswith(
            (
                "energy_agent.memory.session_store",
                "energy_agent.model.gateway",
                "energy_agent.tools.executor",
                "energy_agent.tools.registry",
            )
        ):
            add(line, "agent-capability-contract-only", module)
        if relative.startswith("guardrails/") and module.startswith("energy_agent.agent"):
            add(line, "guardrails-no-agent", module)
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


def logical_module_cycles() -> list[list[str]]:
    edges: dict[str, set[str]] = {module: set() for module in LOGICAL_MODULES}
    for path in sorted(SRC.rglob("*.py")):
        relative = path.relative_to(SRC).as_posix()
        if not is_application_graph_file(relative):
            continue
        source = relative.split("/", 1)[0]
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for _, imported in imported_modules(tree):
            if not imported.startswith("energy_agent."):
                continue
            target = imported.split(".", 2)[1]
            if target in LOGICAL_MODULES and target != source:
                edges[source].add(target)

    cycles: set[tuple[str, ...]] = set()

    def visit(start: str, current: str, path: list[str]) -> None:
        for target in edges[current]:
            if target == start:
                ring = path[:]
                rotations = [tuple(ring[index:] + ring[:index]) for index in range(len(ring))]
                cycles.add(min(rotations))
            elif target not in path:
                visit(start, target, [*path, target])

    for module in sorted(LOGICAL_MODULES):
        visit(module, module, [module])
    return [list(cycle) for cycle in sorted(cycles)]


def main() -> int:
    violations: list[Violation] = []
    for path in sorted(SRC.rglob("*.py")):
        violations.extend(check_python(path))
    for cycle in logical_module_cycles():
        violations.append(
            Violation(
                Path("src/energy_agent"),
                1,
                "logical-module-cycle",
                " -> ".join([*cycle, cycle[0]]),
            )
        )
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
