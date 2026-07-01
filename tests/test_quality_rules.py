"""用 AST 验证公共注释完整性和模块依赖边界。"""

import ast
import importlib.util
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).parents[1] / "src" / "energy_agent_diagnosis"
LOGIC_PACKAGES = {"agent", "retrieval", "tools", "memory"}
ALLOWED_LOGIC_IMPORT_PREFIXES = (
    "energy_agent_diagnosis.contracts",
    "energy_agent_diagnosis.memory",
    "energy_agent_diagnosis.ports",
    "energy_agent_diagnosis.core.module",
    "energy_agent_diagnosis.retrieval",
    "energy_agent_diagnosis.tools",
)
ALLOWED_LOGIC_THIRD_PARTY_ROOTS = {"langgraph"}


def python_sources() -> list[Path]:
    """返回项目中的全部生产 Python 源文件。"""
    return sorted(SOURCE_ROOT.rglob("*.py"))


def test_public_code_has_docstrings() -> None:
    missing: list[str] = []
    for path in python_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if ast.get_docstring(tree) is None:
            missing.append(f"{path}:module")
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("_"):
                    continue
                if ast.get_docstring(node) is None:
                    missing.append(f"{path}:{node.lineno}:{node.name}")
    assert missing == []


def test_logic_modules_do_not_import_infrastructure() -> None:
    violations: list[str] = []
    for package in LOGIC_PACKAGES:
        for path in (SOURCE_ROOT / package).rglob("*.py"):
            relative = path.relative_to(SOURCE_ROOT).with_suffix("")
            module_parts = list(relative.parts)
            if module_parts[-1] == "__init__":
                module_parts.pop()
            module_name = ".".join(("energy_agent_diagnosis", *module_parts))
            current_package = (
                module_name if path.name == "__init__.py" else module_name.rpartition(".")[0]
            )
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    imported_name = node.module or ""
                    if node.level:
                        imported_name = importlib.util.resolve_name(
                            "." * node.level + imported_name,
                            current_package,
                        )
                    imported = [imported_name]
                else:
                    continue
                for name in imported:
                    same_logic_package = name.startswith(f"energy_agent_diagnosis.{package}.")
                    project_import_forbidden = name.startswith("energy_agent_diagnosis") and not (
                        name.startswith(ALLOWED_LOGIC_IMPORT_PREFIXES) or same_logic_package
                    )
                    root_name = name.split(".", maxsplit=1)[0]
                    third_party_forbidden = (
                        not name.startswith("energy_agent_diagnosis")
                        and root_name not in sys.stdlib_module_names
                        and root_name not in ALLOWED_LOGIC_THIRD_PARTY_ROOTS
                        and root_name != "__future__"
                    )
                    if project_import_forbidden or third_party_forbidden:
                        violations.append(f"{path}:{node.lineno}:{name}")
    assert violations == []
