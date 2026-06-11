import json
import importlib.util
import sys
import types
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
HOST_POLICY_PLUGIN_DIRS = [
    REPO_ROOT / "server/apps/monitor/support-files/plugins/Telegraf/http/host",
    REPO_ROOT / "server/apps/monitor/support-files/plugins/Telegraf/http/windows_wmi",
]
POLICY_MIGRATE_PATH = REPO_ROOT / "server/apps/monitor/management/services/policy_migrate.py"


def _install_module(monkeypatch, name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def _load_policy_migrate_module(monkeypatch):
    _install_module(monkeypatch, "apps")
    _install_module(monkeypatch, "apps.core")
    _install_module(monkeypatch, "apps.core.logger", monitor_logger=types.SimpleNamespace(info=lambda *args, **kwargs: None, error=lambda *args, **kwargs: None))
    _install_module(monkeypatch, "apps.monitor")
    _install_module(monkeypatch, "apps.monitor.constants")
    _install_module(monkeypatch, "apps.monitor.constants.plugin", PluginConstants=types.SimpleNamespace(DIRECTORY="", ENTERPRISE_DIRECTORY=""))
    _install_module(monkeypatch, "apps.monitor.management")
    _install_module(monkeypatch, "apps.monitor.management.utils", find_files_by_pattern=lambda *args, **kwargs: [])
    _install_module(monkeypatch, "apps.monitor.services")
    _install_module(monkeypatch, "apps.monitor.services.policy", PolicyService=types.SimpleNamespace(import_monitor_policy=lambda data: None))

    spec = importlib.util.spec_from_file_location("monitor_policy_migrate_test_module", POLICY_MIGRATE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_migrate_policy_skips_empty_policy_file(tmp_path, monkeypatch):
    policy_migrate = _load_policy_migrate_module(monkeypatch)
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps([]), encoding="utf-8")
    find_results = iter([[str(policy_path)], []])
    imported = []

    monkeypatch.setattr(policy_migrate, "find_files_by_pattern", lambda *args, **kwargs: next(find_results))
    monkeypatch.setattr(policy_migrate.PolicyService, "import_monitor_policy", imported.append)

    policy_migrate.migrate_policy()

    assert imported == []


def _collect_policy_metric_names(policy_data):
    return [template["metric_name"] for template in policy_data["templates"]]


def test_host_policy_templates_reference_existing_plugin_metrics():
    for plugin_dir in HOST_POLICY_PLUGIN_DIRS:
        metrics_data = json.loads((plugin_dir / "metrics.json").read_text(encoding="utf-8"))
        policy_data = json.loads((plugin_dir / "policy.json").read_text(encoding="utf-8"))
        metric_names = {metric["name"] for metric in metrics_data["metrics"]}
        policy_metric_names = _collect_policy_metric_names(policy_data)

        assert policy_metric_names, f"{plugin_dir}/policy.json should define alert templates"
        assert [name for name in policy_metric_names if name not in metric_names] == []
