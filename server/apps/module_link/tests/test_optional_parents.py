import ast
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]


def _module_level_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def test_tasks_do_not_import_parent_services_at_module_level():
    modules = _module_level_imports(APP_ROOT / "tasks.py")
    assert modules == ["celery", "apps.core.logger"]


def test_recycle_skips_when_either_parent_missing(monkeypatch):
    from apps.module_link.tasks import recycle_expired_cmdb_monitor_tasks

    monkeypatch.setattr("django.apps.apps.is_installed", lambda name: name == "apps.cmdb")
    assert recycle_expired_cmdb_monitor_tasks() == 0

    monkeypatch.setattr("django.apps.apps.is_installed", lambda name: name == "apps.monitor")
    assert recycle_expired_cmdb_monitor_tasks() == 0

    monkeypatch.setattr("django.apps.apps.is_installed", lambda name: False)
    assert recycle_expired_cmdb_monitor_tasks() == 0
