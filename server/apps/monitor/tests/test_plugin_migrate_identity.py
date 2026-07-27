import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.monitor.management.services import plugin_migrate
from apps.monitor.models import MonitorPlugin


def _write_plugin(tmp_path, relative_dir, metrics_extra=None, ui_data=None, template_text=None):
    plugin_dir = tmp_path / "plugins" / relative_dir
    plugin_dir.mkdir(parents=True)

    metrics_data = {
        "plugin": "Vendor SNMP",
        "plugin_desc": "desc",
        "name": "Switch",
        "metrics": [],
    }
    metrics_data.update(metrics_extra or {})
    metrics_path = plugin_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics_data), encoding="utf-8")

    if ui_data is not None:
        (plugin_dir / "UI.json").write_text(json.dumps(ui_data), encoding="utf-8")

    if template_text is not None:
        (plugin_dir / "vendor.child.toml.j2").write_text(template_text, encoding="utf-8")

    return metrics_path


def _capture_imported_plugins(monkeypatch):
    imported = []
    monkeypatch.setattr(plugin_migrate.MonitorPluginService, "import_monitor_plugin", lambda data: imported.append(dict(data)))
    return imported


def test_import_uses_explicit_identity_before_path_fallback(tmp_path, monkeypatch):
    metrics_path = _write_plugin(
        tmp_path,
        Path("Telegraf") / "snmp" / "a10_loadbalance_thunder",
        metrics_extra={
            "collector": "Telegraf",
            "collect_type": "snmp_a10",
        },
    )
    imported = _capture_imported_plugins(monkeypatch)

    success_count, error_count, _ = plugin_migrate._import_plugins_from_files([str(metrics_path)])

    assert success_count == 1
    assert error_count == 0
    assert imported[0]["collector"] == "Telegraf"
    assert imported[0]["collect_type"] == "snmp_a10"


def test_expand_local_template_assets_embeds_sibling_file(tmp_path):
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    (plugin_dir / "normalizer.star").write_text("def apply(metric):\n    return metric\n", encoding="utf-8")
    template = "source = '''\n# @bk_include_file normalizer.star\n'''"

    expanded = plugin_migrate._expand_local_template_assets(template, plugin_dir)

    assert "# @bk_include_file" not in expanded
    assert "def apply(metric):" in expanded


def test_expand_local_template_assets_rejects_parent_path(tmp_path):
    with pytest.raises(ValueError, match="非法的插件资源路径"):
        plugin_migrate._expand_local_template_assets(
            "# @bk_include_file ../normalizer.star",
            tmp_path,
        )


def test_process_config_templates_embeds_local_assets(tmp_path):
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    (plugin_dir / "normalizer.star").write_text("def apply(metric):\n    return metric\n", encoding="utf-8")
    (plugin_dir / "vendor.child.toml.j2").write_text(
        "source = '''\n# @bk_include_file normalizer.star\n'''",
        encoding="utf-8",
    )

    created, updated, deleted = plugin_migrate._process_config_templates(
        plugin_dir,
        MonitorPlugin(name="test-plugin"),
        {},
    )

    assert len(created) == 1
    assert "def apply(metric):" in created[0].content
    assert updated == []
    assert deleted == []


def test_process_config_templates_preserves_existing_template_when_asset_is_missing(tmp_path):
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    (plugin_dir / "vendor.child.toml.j2").write_text(
        "source = '''\n# @bk_include_file missing.star\n'''",
        encoding="utf-8",
    )
    existing = SimpleNamespace(id=123, content="previous-good-template")

    created, updated, deleted = plugin_migrate._process_config_templates(
        plugin_dir,
        MonitorPlugin(name="test-plugin"),
        {("vendor", "child", "toml"): existing},
    )

    assert created == []
    assert updated == []
    assert deleted == []
    assert existing.content == "previous-good-template"


def test_import_uses_path_fallback_when_identity_fields_are_absent(tmp_path, monkeypatch):
    metrics_path = _write_plugin(
        tmp_path,
        Path("Telegraf") / "snmp_cisco" / "switch",
    )
    imported = _capture_imported_plugins(monkeypatch)

    success_count, error_count, _ = plugin_migrate._import_plugins_from_files([str(metrics_path)])

    assert success_count == 1
    assert error_count == 0
    assert imported[0]["collector"] == "Telegraf"
    assert imported[0]["collect_type"] == "snmp_cisco"


@pytest.mark.parametrize(
    ("metrics_extra", "expected_collector", "expected_collect_type"),
    [
        ({"collector": "Custom-Exporter"}, "Custom-Exporter", "snmp"),
        ({"collect_type": "snmp_a10"}, "Telegraf", "snmp_a10"),
        ({"collector": "", "collect_type": "snmp_a10"}, "Telegraf", "snmp_a10"),
    ],
)
def test_import_falls_back_per_missing_or_empty_identity_field(tmp_path, monkeypatch, metrics_extra, expected_collector, expected_collect_type):
    metrics_path = _write_plugin(
        tmp_path,
        Path("Telegraf") / "snmp" / "vendor",
        metrics_extra=metrics_extra,
    )
    imported = _capture_imported_plugins(monkeypatch)

    success_count, error_count, _ = plugin_migrate._import_plugins_from_files([str(metrics_path)])

    assert success_count == 1
    assert error_count == 0
    assert imported[0]["collector"] == expected_collector
    assert imported[0]["collect_type"] == expected_collect_type


def test_import_rejects_ui_identity_conflict(tmp_path, monkeypatch):
    metrics_path = _write_plugin(
        tmp_path,
        Path("Telegraf") / "snmp" / "vendor",
        metrics_extra={
            "collector": "Telegraf",
            "collect_type": "snmp_a10",
        },
        ui_data={
            "collector": "Telegraf",
            "collect_type": "snmp_wrong",
        },
    )
    imported = _capture_imported_plugins(monkeypatch)

    success_count, error_count, _ = plugin_migrate._import_plugins_from_files([str(metrics_path)])

    assert success_count == 0
    assert error_count == 1
    assert imported == []


def test_import_rejects_template_collect_type_conflict(tmp_path, monkeypatch):
    metrics_path = _write_plugin(
        tmp_path,
        Path("Telegraf") / "snmp" / "vendor",
        metrics_extra={
            "collector": "Telegraf",
            "collect_type": "snmp_a10",
        },
        template_text='[[inputs.snmp.tags]]\ncollect_type = "snmp_wrong"\n',
    )
    imported = _capture_imported_plugins(monkeypatch)

    success_count, error_count, _ = plugin_migrate._import_plugins_from_files([str(metrics_path)])

    assert success_count == 0
    assert error_count == 1
    assert imported == []


@pytest.mark.django_db
def test_migrate_plugin_is_idempotent_with_explicit_identity(tmp_path, monkeypatch):
    metrics_path = _write_plugin(
        tmp_path,
        Path("Telegraf") / "snmp" / "vendor",
        metrics_extra={
            "plugin": "Vendor Explicit SNMP",
            "plugin_desc": "desc",
            "collector": "Telegraf",
            "collect_type": "snmp_a10",
            "status_query": "any({collect_type='snmp_a10'}) by (instance_id)",
            "default_metric": "vendor_metric",
            "instance_id_keys": ["instance_id"],
            "metrics": [
                {
                    "metric_group": "Availability",
                    "name": "vendor_status",
                    "display_name": "Vendor Status",
                    "query": "vendor_status",
                    "unit": "",
                    "data_type": "Number",
                    "description": "",
                    "dimensions": [],
                    "instance_id_keys": ["instance_id"],
                }
            ],
        },
        ui_data={
            "collector": "Telegraf",
            "collect_type": "snmp_a10",
        },
        template_text='[[inputs.snmp.tags]]\ncollect_type = "snmp_a10"\n',
    )
    monkeypatch.setattr(plugin_migrate.PluginConstants, "DIRECTORY", str(metrics_path.parents[3]))
    monkeypatch.setattr(plugin_migrate.PluginConstants, "ENTERPRISE_DIRECTORY", str(tmp_path / "missing-enterprise-plugins"))

    plugin_migrate.migrate_plugin()
    plugin_migrate.migrate_plugin()

    from apps.monitor.models import MonitorObject, MonitorPlugin, MonitorPluginConfigTemplate, MonitorPluginUITemplate
    from apps.monitor.models.monitor_metrics import Metric, MetricGroup

    plugin = MonitorPlugin.objects.get(name="Vendor Explicit SNMP")

    assert plugin.collector == "Telegraf"
    assert plugin.collect_type == "snmp_a10"
    assert MonitorPlugin.objects.filter(name="Vendor Explicit SNMP").count() == 1
    assert MonitorPluginConfigTemplate.objects.filter(plugin=plugin).count() == 1
    assert MonitorPluginUITemplate.objects.filter(plugin=plugin).count() == 1
    assert MetricGroup.objects.filter(monitor_plugin=plugin, name="Availability").count() == 1
    assert Metric.objects.filter(monitor_plugin=plugin, name="vendor_status").count() == 1
    assert MonitorObject.objects.get(name="Switch").is_builtin is True
