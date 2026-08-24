import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SERVER_APPS = Path(__file__).resolve().parents[2]
ALLOWED_GETLOGGER = {
    "core/logger.py",
    "core/exceptions/base_app_exception.py",
}
EXPECTED_APP_LOGGERS = {
    "apm": {"apm_logger", "celery_logger"},
    "alerts": {"alert_logger"},
    "cmdb": {"cmdb_logger"},
    "console_mgmt": {"console_mgmt_logger", "opspilot_logger"},
    "core": {"logger", "celery_logger", "nats_logger", "openapi_logger", "opspilot_logger"},
    "job_mgmt": {"job_logger"},
    "log": {"log_logger", "celery_logger", "logger"},
    "mlops": {"mlops_logger"},
    "monitor": {"monitor_logger", "celery_logger", "nats_logger"},
    "node_mgmt": {"node_logger", "celery_logger", "logger"},
    "operation_analysis": {"operation_analysis_logger"},
    "opspilot": {"opspilot_logger", "cmdb_logger", "logger"},
    "patch_mgmt": {"patch_mgmt_logger", "logger"},
    "rpc": {"logger"},
    "system_mgmt": {"system_mgmt_logger", "logger"},
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


def test_central_logger_aliases_match_the_owning_app():
    violations = []
    for path in SERVER_APPS.rglob("*.py"):
        relative = path.relative_to(SERVER_APPS)
        if "tests" in relative.parts or relative.parts[0] not in EXPECTED_APP_LOGGERS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(relative))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.module != "apps.core.logger":
                continue
            for name in node.names:
                routes_as_logger = name.asname == "logger" or (name.name == "logger" and name.asname is None)
                if routes_as_logger and name.name not in EXPECTED_APP_LOGGERS[relative.parts[0]]:
                    violations.append(f"{relative.as_posix()}:{node.lineno}:{name.name}")

    assert violations == []
