import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SERVER_APPS = Path(__file__).resolve().parents[2]
ALLOWED_GETLOGGER = {
    "core/logger.py",
    "core/exceptions/base_app_exception.py",
}


def test_server_apps_production_uses_central_logger_sources():
    violations = []
    for path in SERVER_APPS.rglob("*.py"):
        relative = path.relative_to(SERVER_APPS).as_posix()
        if "/tests/" in f"/{relative}" or relative in ALLOWED_GETLOGGER:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "getLogger":
                violations.append(f"{relative}:{node.lineno}")

    assert violations == []


def test_core_celery_utils_does_not_route_logs_to_another_app():
    source = (SERVER_APPS / "core/utils/celery_utils.py").read_text(encoding="utf-8")

    assert "from apps.core.logger import logger" in source
    assert "opspilot_logger" not in source
