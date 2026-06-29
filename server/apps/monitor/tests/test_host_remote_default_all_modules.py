# -*- coding: utf-8 -*-
import json
from pathlib import Path

import pytest
import yaml

from apps.monitor.management.services import plugin_migrate
from apps.monitor.models import CollectConfig, MonitorObject, MonitorPlugin
from apps.monitor.models.monitor_object import MonitorInstance


REPO_ROOT = Path(__file__).resolve().parents[4]
MONITOR_ROOT = REPO_ROOT / "server/apps/monitor"
ALL_MODULES = ["cpu", "mem", "disk", "diskio", "net", "processes", "system"]
ALL_MODULES_CSV = ",".join(ALL_MODULES)

HOST_UI = MONITOR_ROOT / "support-files/plugins/Telegraf/http/host/UI.json"
WINDOWS_WMI_UI = MONITOR_ROOT / "support-files/plugins/Telegraf/http/windows_wmi/UI.json"
HOST_TEMPLATE = MONITOR_ROOT / "support-files/plugins/Telegraf/http/host/host.child.toml.j2"
WINDOWS_WMI_TEMPLATE = MONITOR_ROOT / "support-files/plugins/Telegraf/http/windows_wmi/windows_wmi.child.toml.j2"
HOST_METRICS = MONITOR_ROOT / "support-files/plugins/Telegraf/http/host/metrics.json"
WINDOWS_WMI_METRICS = MONITOR_ROOT / "support-files/plugins/Telegraf/http/windows_wmi/metrics.json"
ZH_LANG = MONITOR_ROOT / "language/zh-Hans.yaml"
EN_LANG = MONITOR_ROOT / "language/en.yaml"
STARGAZER_MONITOR = REPO_ROOT / "agents/stargazer/api/monitor.py"


def _load_json(path):
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _load_yaml(path):
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _field_by_name(ui, name):
    return next(field for field in ui["form_fields"] if field["name"] == name)


def _metric_names(path):
    return {metric["name"] for metric in _load_json(path)["metrics"]}


def _metric_groups(path):
    return {metric["metric_group"] for metric in _load_json(path)["metrics"]}


def _source_block(content, start_marker):
    start = content.index(start_marker)
    block_end = len(content)
    for marker in ("\n@monitor_router.", "\nasync def ", "\ndef ", "\nclass "):
        next_marker = content.find(marker, start + len(start_marker))
        if next_marker != -1:
            block_end = min(block_end, next_marker)
    return content[start:block_end]


@pytest.mark.parametrize("path", [HOST_UI, WINDOWS_WMI_UI])
def test_remote_host_plugin_ui_hides_metrics_modules(path):
    ui = _load_json(path)

    field = _field_by_name(ui, "metrics_modules")

    assert field["type"] == "hidden"
    assert field["default_value"] == ALL_MODULES
    assert field.get("options") is None
    assert field.get("label") is None


@pytest.mark.parametrize("path", [HOST_TEMPLATE, WINDOWS_WMI_TEMPLATE])
def test_remote_host_child_templates_default_to_full_modules(path):
    content = path.read_text(encoding="utf-8")

    assert f"default('{ALL_MODULES_CSV}', true)" in content
    assert "default('cpu,mem,disk,net', true)" not in content


def test_stargazer_monitor_api_defaults_to_full_modules():
    content = STARGAZER_MONITOR.read_text(encoding="utf-8")
    host_metrics_block = _source_block(content, "async def host_metrics")

    assert f'request.headers.get("metrics_modules", "{ALL_MODULES_CSV}")' in host_metrics_block
    assert 'request.headers.get("metrics_modules", "cpu,mem,disk,net")' not in host_metrics_block


@pytest.mark.parametrize("lang_path", [ZH_LANG, EN_LANG])
def test_remote_host_metric_groups_and_names_are_bilingual(lang_path):
    lang = _load_yaml(lang_path)
    host_groups = lang["monitor_object_metric_group"]["Host"]
    host_metrics = lang["monitor_object_metric"]["Host"]

    required_groups = _metric_groups(HOST_METRICS) | _metric_groups(WINDOWS_WMI_METRICS)
    required_metrics = _metric_names(HOST_METRICS) | _metric_names(WINDOWS_WMI_METRICS)

    missing_groups = sorted(required_groups - set(host_groups))
    missing_metrics = sorted(required_metrics - set(host_metrics))
    empty_groups = sorted(group for group in required_groups if not str(host_groups.get(group, "")).strip())
    invalid_metrics = sorted(
        metric
        for metric in required_metrics
        if not isinstance(host_metrics.get(metric), dict)
        or not str(host_metrics[metric].get("name", "")).strip()
        or not str(host_metrics[metric].get("desc", "")).strip()
    )

    assert missing_groups == []
    assert empty_groups == []
    assert missing_metrics == []
    assert invalid_metrics == []


@pytest.mark.parametrize("metrics_modules", ["cpu,mem,disk,net", "cpu,mem", "cpu"])
def test_replace_metrics_modules_line_forces_full_modules_and_is_idempotent(metrics_modules):
    original = (
        '[[inputs.prometheus]]\n'
        '    urls = ["${STARGAZER_URL}/api/monitor/host/metrics"]\n'
        '    [inputs.prometheus.http_headers]\n'
        f'        metrics_modules = "{metrics_modules}"\n'
        '        collect_type = "http"\n'
    )

    updated, changed = plugin_migrate._replace_remote_host_metrics_modules_line(original)
    updated_again, changed_again = plugin_migrate._replace_remote_host_metrics_modules_line(updated)

    assert changed is True
    assert f'metrics_modules = "{ALL_MODULES_CSV}"' in updated
    assert f'metrics_modules = "{metrics_modules}"' not in updated
    assert updated_again == updated
    assert changed_again is False


def test_replace_metrics_modules_line_ignores_missing_and_commented_lines():
    content = (
        '[[inputs.prometheus]]\n'
        '    # metrics_modules = "cpu,mem,disk,net"\n'
        '    collect_type = "http"\n'
    )

    updated, changed = plugin_migrate._replace_remote_host_metrics_modules_line(content)

    assert updated == content
    assert changed is False


def test_migrate_plugin_invokes_remote_host_metrics_module_sync(monkeypatch):
    calls = []

    monkeypatch.setattr(plugin_migrate, "find_files_by_pattern", lambda *args, **kwargs: [])
    monkeypatch.setattr(plugin_migrate, "_import_plugins_from_files", lambda path_list: (0, 0, {}))
    monkeypatch.setattr(plugin_migrate, "_load_plugins_to_memory", lambda: {})
    monkeypatch.setattr(plugin_migrate, "_load_templates_to_memory", lambda: ({}, {}))
    monkeypatch.setattr(
        plugin_migrate,
        "_collect_templates_to_process",
        lambda *args: {"config": ([], [], []), "ui": ([], [], [])},
    )
    monkeypatch.setattr(
        plugin_migrate,
        "_batch_save_templates",
        lambda templates_data: {
            "config_create": 0,
            "config_update": 0,
            "config_delete": 0,
            "ui_create": 0,
            "ui_update": 0,
            "ui_delete": 0,
        },
    )
    monkeypatch.setattr(plugin_migrate, "_cleanup_removed_plugins", lambda path_list: None)
    monkeypatch.setattr(plugin_migrate, "_cleanup_orphan_objects", lambda: None)
    monkeypatch.setattr(plugin_migrate, "_reconcile_supplementary_indicators", lambda supplementary_map: 0)
    monkeypatch.setattr(plugin_migrate, "_cleanup_empty_builtin_metric_groups", lambda: None)
    monkeypatch.setattr(
        plugin_migrate,
        "_sync_remote_host_metrics_modules",
        lambda: calls.append("sync") or 0,
        raising=False,
    )

    plugin_migrate.migrate_plugin()

    assert calls == ["sync"]


@pytest.mark.django_db
def test_sync_remote_host_child_configs_updates_only_host_remote_and_wmi(monkeypatch):
    monitor_object = MonitorObject.objects.create(name="Host")
    plugin = MonitorPlugin.objects.create(name="Host Remote", collector="Telegraf", collect_type="http")

    def create_collect_config(config_id, instance_id, collect_type, config_type, is_child):
        instance = MonitorInstance.objects.create(
            id=instance_id,
            name=instance_id,
            monitor_object=monitor_object,
        )
        CollectConfig.objects.create(
            id=config_id,
            monitor_instance=instance,
            monitor_plugin=plugin,
            collector="Telegraf",
            collect_type=collect_type,
            config_type=config_type,
            file_type="toml",
            is_child=is_child,
        )

    create_collect_config("sync-host", "host-1", "http", "host", True)
    create_collect_config("sync-wmi", "host-2", "http", "windows_wmi", True)
    create_collect_config("skip-snmp", "host-3", "snmp", "host", True)
    create_collect_config("skip-base", "host-4", "http", "host", False)
    create_collect_config("skip-other", "host-5", "http", "other", True)

    child_contents = {
        "sync-host": 'metrics_modules = "cpu,mem,disk,net"\n',
        "sync-wmi": 'metrics_modules = "cpu,mem,disk,net"\n',
        "skip-snmp": 'metrics_modules = "cpu,mem,disk,net"\n',
        "skip-base": 'metrics_modules = "cpu,mem,disk,net"\n',
        "skip-other": 'metrics_modules = "cpu,mem,disk,net"\n',
    }
    requested_ids = []
    updates = {}

    class FakeNodeMgmt:
        def get_child_configs_by_ids(self, ids):
            requested_ids.extend(ids)
            return [{"id": config_id, "content": child_contents[config_id]} for config_id in ids]

        def update_child_config_content(self, config_id, content, env_config=None):
            updates[config_id] = content
            child_contents[config_id] = content

    monkeypatch.setattr(plugin_migrate, "NodeMgmt", FakeNodeMgmt, raising=False)

    updated_count = plugin_migrate._sync_remote_host_metrics_modules()
    updated_count_again = plugin_migrate._sync_remote_host_metrics_modules()

    assert updated_count == 2
    assert updated_count_again == 0
    assert set(requested_ids) == {"sync-host", "sync-wmi"}
    assert set(updates) == {"sync-host", "sync-wmi"}
    assert updates["sync-host"] == f'metrics_modules = "{ALL_MODULES_CSV}"\n'
    assert updates["sync-wmi"] == f'metrics_modules = "{ALL_MODULES_CSV}"\n'
