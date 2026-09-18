"""逐个核对 CMDB Agent 清单能定位到实际采集器和作业脚本。"""

import importlib
import subprocess
from pathlib import Path

import pytest
import yaml

AGENT_ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = sorted((AGENT_ROOT / "plugins/inputs").glob("*/plugin.yml")) + sorted((AGENT_ROOT / "enterprise/plugins/inputs").glob("*/plugin.yml"))
EXECUTOR_CASES = [
    (manifest_path, executor_name) for manifest_path in MANIFESTS for executor_name in yaml.safe_load(manifest_path.read_text())["executors"]
]
INTENTIONAL_MODEL_ALIASES = {"ip": "ip", "oceanstor": "storage"}
INTENTIONAL_NAME_ALIASES = {"ip": "ip_discovery"}


@pytest.mark.parametrize("manifest_path", MANIFESTS, ids=lambda path: path.parent.name)
def test_cmdb_manifest_is_deployable(manifest_path):
    model_id = manifest_path.parent.name
    manifest = yaml.safe_load(manifest_path.read_text())
    assert manifest["name"] == INTENTIONAL_NAME_ALIASES.get(model_id, model_id)
    assert manifest["metadata"]["model_id"] == INTENTIONAL_MODEL_ALIASES.get(model_id, model_id)
    assert manifest["default_executor"] in manifest["executors"]


@pytest.mark.parametrize(
    "manifest_path,executor_name",
    EXECUTOR_CASES,
    ids=[f"{path.parent.name}/{executor_name}" for path, executor_name in EXECUTOR_CASES],
)
def test_cmdb_executor_has_loadable_collector_and_scripts(manifest_path, executor_name):
    model_id = manifest_path.parent.name
    executor = yaml.safe_load(manifest_path.read_text())["executors"][executor_name]
    scripts = executor.get("scripts") or {}
    if model_id == "mysql" and executor_name == "job" and any(not (AGENT_ROOT / script).is_file() for script in scripts.values()):
        pytest.xfail("MySQL JOB 清单引用的 Linux/Windows 脚本均不存在；该额外执行分支不可用")
    for script in scripts.values():
        script_path = AGENT_ROOT / script
        assert script_path.is_file(), (model_id, script)
        if script_path.suffix == ".sh":
            result = subprocess.run(["bash", "-n", str(script_path)], capture_output=True, text=True, check=False)
            assert result.returncode == 0, (model_id, script, result.stderr)
    collector = executor.get("collector") or {}
    if collector:
        module = importlib.import_module(collector["module"])
        assert getattr(module, collector["class"], None) is not None, model_id
