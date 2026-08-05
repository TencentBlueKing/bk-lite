import ast
from pathlib import Path

import pytest


APPS_ROOT = Path(__file__).resolve().parents[2]
ALLOWED_ENVIRONMENT_MODULE = APPS_ROOT / "core" / "utils" / "safe_template.py"
pytestmark = pytest.mark.integration


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else None
    return None


def _ordinary_environment_references(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    environment_attributes = {"jinja2.Environment", "jinja2.environment.Environment"}
    violations = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "jinja2" and alias.asname:
                    environment_attributes.add(f"{alias.asname}.Environment")
                    environment_attributes.add(f"{alias.asname}.environment.Environment")
                elif alias.name == "jinja2.environment" and alias.asname:
                    environment_attributes.add(f"{alias.asname}.Environment")
        elif isinstance(node, ast.ImportFrom) and node.module in {"jinja2", "jinja2.environment"}:
            if any(alias.name in {"Environment", "*"} for alias in node.names):
                violations.append(node.lineno)
            if node.module == "jinja2":
                for alias in node.names:
                    if alias.name == "environment":
                        environment_attributes.add(f"{alias.asname or alias.name}.Environment")
        elif isinstance(node, ast.Attribute) and _dotted_name(node) in environment_attributes:
            violations.append(node.lineno)

    return violations


def test_production_code_does_not_reference_ordinary_jinja_environment():
    violations = []
    for path in APPS_ROOT.rglob("*.py"):
        if path == ALLOWED_ENVIRONMENT_MODULE or "tests" in path.parts or "migrations" in path.parts:
            continue
        for line in _ordinary_environment_references(path):
            violations.append(f"{path.relative_to(APPS_ROOT)}:{line}")

    assert violations == [], "普通 jinja2.Environment 必须通过 Core 安全工厂收口：\n" + "\n".join(violations)


@pytest.mark.parametrize(
    "source",
    (
        "import jinja2\njinja2.Environment()",
        "import jinja2 as j2\nj2.Environment()",
        "import jinja2 as j2\nj2.environment.Environment()",
        "import jinja2.environment\njinja2.environment.Environment()",
        "import jinja2.environment as je\nje.Environment()",
        "from jinja2 import environment as je\nje.Environment()",
        "from jinja2.environment import Environment as Env",
    ),
)
def test_detector_covers_ordinary_environment_import_forms(tmp_path, source):
    path = tmp_path / "environment_reference.py"
    path.write_text(source, encoding="utf-8")

    assert _ordinary_environment_references(path)
