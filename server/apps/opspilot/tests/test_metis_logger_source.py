"""Regression: server/apps 内嵌 metis 不得再直接使用 loguru logger。"""

from pathlib import Path

APPS_ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN = "from loguru import logger"


def test_server_apps_do_not_import_loguru_logger():
    offenders = []
    for path in APPS_ROOT.rglob("*.py"):
        if "tests" in path.parts or "migrations" in path.parts:
            continue
        if FORBIDDEN in path.read_text(encoding="utf-8"):
            offenders.append(str(path.relative_to(APPS_ROOT)))
    assert offenders == []


def test_metis_sql_guard_uses_opspilot_logger():
    source = (APPS_ROOT / "opspilot/metis/llm/tools/common/sql_guard.py").read_text(encoding="utf-8")
    assert "from apps.core.logger import opspilot_logger as logger" in source
    assert FORBIDDEN not in source
