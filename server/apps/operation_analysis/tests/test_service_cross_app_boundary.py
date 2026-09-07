import ast
from pathlib import Path

SERVICES_ROOT = Path(__file__).resolve().parents[1] / "services"
FORBIDDEN_MODULES = (
    "apps.cmdb.services",
    "apps.cmdb.graph",
    "apps.cmdb.utils.permission_util",
    "apps.monitor.models",
    "apps.monitor.views",
    "apps.monitor.services",
)
ALLOWLIST = {
    "application3d/query_service.py",
    "application3d/relations.py",
    "application3d/presenters.py",
    "application3d/metric_fields.py",
}


def _imported_modules(tree: ast.AST) -> list[str]:
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
            for alias in node.names:
                names.append(f"{node.module}.{alias.name}")
    return names


def _is_forbidden(module_name: str) -> bool:
    return any(module_name == prefix or module_name.startswith(f"{prefix}.") for prefix in FORBIDDEN_MODULES)


def test_operation_analysis_services_do_not_import_cmdb_or_monitor_internals():
    offenders = []
    for path in SERVICES_ROOT.rglob("*.py"):
        relative = path.relative_to(SERVICES_ROOT).as_posix()
        if relative in ALLOWLIST:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        for module_name in _imported_modules(tree):
            if _is_forbidden(module_name):
                offenders.append(f"{relative}: {module_name}")

    assert offenders == []
