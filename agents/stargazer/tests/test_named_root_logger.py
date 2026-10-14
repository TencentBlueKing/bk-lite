"""Regression: Stargazer adapters must not bind the named root child logger."""

import re
from pathlib import Path

STARGAZER_ROOT = Path(__file__).resolve().parents[1]
NAMED_ROOT_LOGGER = re.compile(r"""getLogger\(\s*['"]root['"]\s*\)""")


def test_stargazer_modules_do_not_bind_named_root_logger():
    offenders = []
    for path in STARGAZER_ROOT.rglob("*.py"):
        if ".venv" in path.parts or "__pycache__" in path.parts or "tests" in path.parts:
            continue
        if NAMED_ROOT_LOGGER.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(STARGAZER_ROOT)))
    assert offenders == []


def test_cmp_driver_and_plugin_shim_use_stargazer_logger():
    driver = (STARGAZER_ROOT / "common/cmp/driver.py").read_text(encoding="utf-8")
    shim = (STARGAZER_ROOT / "common/monitor_plugins/core/logger.py").read_text(encoding="utf-8")
    common = (STARGAZER_ROOT / "common/monitor_plugins/core/common.py").read_text(encoding="utf-8")

    assert "from core.logger import logger" in driver
    assert "from core.logger import logger" in common
    assert "from sanic.log import logger" in shim
    assert 'getLogger("monitor")' in shim
