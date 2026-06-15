"""Unit tests for InstanceSearch plugin-badge dedup (集成模板 column).

Regression for the duplicate `MSSQL（Telegraf）` badge: one physical plugin
template surfaces under two keys (modern ``plugin.id`` and the legacy
``(obj_id, collector, collect_type)`` tuple). When an instance reports data
both keys land in ``vm_confs``, so the category split emits the same template
twice — once auto/normal, once as a phantom manual/normal. The dedup helper
collapses same-template entries while preserving genuinely distinct templates.
"""

from apps.monitor.constants.plugin import PluginConstants
from apps.monitor.services.monitor_instance import InstanceSearch


def _plugin(name, collect_type, collect_mode, status, collector="Telegraf"):
    return {
        "name": name,
        "collector": collector,
        "collect_type": collect_type,
        "display_name": f"{name}（Telegraf）",
        "collect_mode": collect_mode,
        "status": status,
    }


def test_collapses_same_template_auto_and_manual_phantom():
    # Arrange: one MSSQL/database template surfaced twice (id + legacy tuple)
    plugins = [
        _plugin("MSSQL", "database", PluginConstants.COLLECT_MODE_AUTO, PluginConstants.STATUS_NORMAL),
        _plugin("MSSQL", "database", PluginConstants.COLLECT_MODE_MANUAL, PluginConstants.STATUS_NORMAL),
    ]

    # Act
    result = InstanceSearch._dedupe_instance_plugins(plugins)

    # Assert: single badge, config-backed auto/normal preferred over manual phantom
    assert len(result) == 1
    assert result[0]["collect_mode"] == PluginConstants.COLLECT_MODE_AUTO
    assert result[0]["status"] == PluginConstants.STATUS_NORMAL


def test_keeps_distinct_templates_exporter_and_database():
    # MSSQL legitimately exposes two different templates — must NOT be collapsed
    plugins = [
        _plugin(
            "MSSQL-Exporter", "exporter",
            PluginConstants.COLLECT_MODE_AUTO, PluginConstants.STATUS_NORMAL,
            collector="MSSQL-Exporter",
        ),
        _plugin("MSSQL", "database", PluginConstants.COLLECT_MODE_AUTO, PluginConstants.STATUS_NORMAL),
    ]

    result = InstanceSearch._dedupe_instance_plugins(plugins)

    assert len(result) == 2
    assert {p["collect_type"] for p in result} == {"exporter", "database"}


def test_prefers_auto_offline_over_manual_normal():
    # auto/offline (db config exists but not reporting) outranks manual phantom
    plugins = [
        _plugin("MSSQL", "database", PluginConstants.COLLECT_MODE_MANUAL, PluginConstants.STATUS_NORMAL),
        _plugin("MSSQL", "database", PluginConstants.COLLECT_MODE_AUTO, PluginConstants.STATUS_OFFLINE),
    ]

    result = InstanceSearch._dedupe_instance_plugins(plugins)

    assert len(result) == 1
    assert result[0]["collect_mode"] == PluginConstants.COLLECT_MODE_AUTO
    assert result[0]["status"] == PluginConstants.STATUS_OFFLINE


def test_single_plugin_unchanged_and_order_preserved():
    plugins = [
        _plugin("Haproxy", "middleware", PluginConstants.COLLECT_MODE_AUTO, PluginConstants.STATUS_NORMAL),
        _plugin(
            "MSSQL-Exporter", "exporter",
            PluginConstants.COLLECT_MODE_AUTO, PluginConstants.STATUS_NORMAL,
            collector="MSSQL-Exporter",
        ),
    ]

    result = InstanceSearch._dedupe_instance_plugins(plugins)

    assert [p["name"] for p in result] == ["Haproxy", "MSSQL-Exporter"]


def test_empty_list_returns_empty():
    assert InstanceSearch._dedupe_instance_plugins([]) == []
