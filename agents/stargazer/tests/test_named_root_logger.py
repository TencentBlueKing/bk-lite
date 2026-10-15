"""Regression: Stargazer adapters must not bind the named root child logger."""

import ast
import re
from pathlib import Path

STARGAZER_ROOT = Path(__file__).resolve().parents[1]
NAMED_ROOT_LOGGER = re.compile(r"""getLogger\(\s*['"]root['"]\s*\)""")
REWRITTEN_MODULES = (
    "common/cmp/driver.py",
    "common/monitor_plugins/core/common.py",
    "common/monitor_plugins/core/logger.py",
    "common/cmp/cloud_apis/resource_apis/cw_aliyun.py",
    "common/cmp/cloud_apis/resource_apis/cw_amazonaws.py",
    "common/cmp/cloud_apis/resource_apis/cw_apsara.py",
    "common/cmp/cloud_apis/resource_apis/cw_cas.py",
    "common/cmp/cloud_apis/resource_apis/cw_easystack.py",
    "common/cmp/cloud_apis/resource_apis/cw_fusioncloud.py",
    "common/cmp/cloud_apis/resource_apis/cw_fusioncompute.py",
    "common/cmp/cloud_apis/resource_apis/cw_openstack.py",
    "common/cmp/cloud_apis/resource_apis/cw_qingcloud.py",
    "common/cmp/cloud_apis/resource_apis/cw_qingcloud_private.py",
    "common/cmp/cloud_apis/resource_apis/cw_sangforhci.py",
    "common/cmp/cloud_apis/resource_apis/cw_tce.py",
    "common/cmp/cloud_apis/resource_apis/cw_tdsql.py",
    "common/cmp/cloud_apis/resource_apis/cw_tke.py",
    "common/cmp/cloud_apis/resource_apis/cw_tsf.py",
    "common/cmp/cloud_apis/resource_apis/cw_vmware.py",
)


def test_stargazer_modules_do_not_bind_named_root_logger():
    offenders = []
    for path in STARGAZER_ROOT.rglob("*.py"):
        if ".venv" in path.parts or "__pycache__" in path.parts or "tests" in path.parts:
            continue
        if NAMED_ROOT_LOGGER.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(STARGAZER_ROOT)))
    assert offenders == []


def test_rewritten_stargazer_modules_parse():
    failures = []
    for relative in REWRITTEN_MODULES:
        path = STARGAZER_ROOT / relative
        try:
            ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            failures.append(f"{relative}:{exc.lineno}: {exc.msg}")
    assert failures == []


def test_cmp_driver_and_plugin_shim_use_stargazer_logger():
    driver = (STARGAZER_ROOT / "common/cmp/driver.py").read_text(encoding="utf-8")
    shim = (STARGAZER_ROOT / "common/monitor_plugins/core/logger.py").read_text(encoding="utf-8")
    common = (STARGAZER_ROOT / "common/monitor_plugins/core/common.py").read_text(encoding="utf-8")

    assert "from core.logger import logger" in driver
    assert "from core.logger import logger" in common
    assert "from sanic.log import logger" in shim
    assert 'getLogger("monitor")' in shim
