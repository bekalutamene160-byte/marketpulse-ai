"""Enforces blueprint 5.4: dependency direction and framework-free inner layers.

    API / worker -> application -> domain + ports -> infrastructure adapters

domain/ and application/ must not import web frameworks or vendor SDKs, and must not reach
outward into api/, infrastructure/, worker/ and the other outer packages. A boundary that is
only documented gets violated within weeks; a boundary that fails the build does not.
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "marketpulse"
PURE_LAYERS = ("domain", "application")

FORBIDDEN_THIRD_PARTY = {
    "fastapi",
    "starlette",
    "uvicorn",
    "sqlalchemy",
    "alembic",
    "psycopg",
    "redis",
    "dramatiq",
    "playwright",
    "httpx",
}
OUTER_PACKAGES = {
    "api",
    "infrastructure",
    "worker",
    "integrations",
    "collectors",
    "agent",
    "workflows",
    "main",
}


def _python_files() -> list[Path]:
    return [p for layer in PURE_LAYERS for p in (SRC / layer).rglob("*.py")]


def _imports(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module)
            if node.module == "marketpulse":  # `from marketpulse import api`
                modules.update(f"marketpulse.{alias.name}" for alias in node.names)
    return modules


def test_the_inner_layers_are_actually_scanned() -> None:
    # Guards against a vacuous pass if the layout moves.
    assert len(_python_files()) >= 5


def test_inner_layers_import_no_web_framework_or_vendor_sdk() -> None:
    violations = [
        f"{path.relative_to(SRC)} imports {module}"
        for path in _python_files()
        for module in _imports(path)
        if module.split(".")[0] in FORBIDDEN_THIRD_PARTY
    ]
    assert not violations, "\n".join(violations)


def test_inner_layers_do_not_depend_on_outer_layers() -> None:
    violations = []
    for path in _python_files():
        for module in _imports(path):
            parts = module.split(".")
            if parts[0] == "marketpulse" and len(parts) > 1 and parts[1] in OUTER_PACKAGES:
                violations.append(f"{path.relative_to(SRC)} imports {module}")
    assert not violations, "\n".join(violations)


def test_domain_does_not_depend_on_the_application_layer() -> None:
    violations = [
        f"{path.relative_to(SRC)} imports {module}"
        for path in (SRC / "domain").rglob("*.py")
        for module in _imports(path)
        if module.startswith("marketpulse.application")
    ]
    assert not violations, "\n".join(violations)
