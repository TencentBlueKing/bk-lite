import json
from pathlib import Path

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models import MonitorPlugin
from apps.monitor.services.instance_facts import InstanceFactResolver


pytestmark = pytest.mark.django_db


def _plugin(bindings):
    return MonitorPlugin.objects.create(name="FactPlugin", instance_fact_bindings=bindings)


def test_local_host_ip_comes_from_trusted_selected_node():
    plugin = _plugin([{
        "fact": "asset.ip",
        "value_type": "ip",
        "resolver": "selected_node",
        "options": {"selection_field": "node_ids", "node_field": "ip"},
    }])

    facts = InstanceFactResolver.resolve(
        plugin,
        {"node_ids": ["n1"], "ip": "192.0.2.99"},
        {"nodes": [{"id": "n1", "name": "collector", "ip": "10.0.41.149"}]},
    )

    assert facts == {"asset.ip": "10.0.41.149"}


def test_remote_host_ip_comes_from_declared_input_not_collector_node():
    plugin = _plugin([{
        "fact": "asset.ip",
        "value_type": "ip",
        "resolver": "input",
        "options": {"field": "host"},
    }])

    facts = InstanceFactResolver.resolve(
        plugin,
        {"host": "203.0.113.8", "node_ids": ["n1"]},
        {"nodes": [{"id": "n1", "ip": "10.0.41.149"}]},
    )

    assert facts == {"asset.ip": "203.0.113.8"}


def test_probe_facts_keep_node_references_and_composed_ipv6_target():
    plugin = _plugin([
        {
            "fact": "collector.nodes",
            "value_type": "node_ref_list",
            "resolver": "selected_nodes",
            "options": {"selection_field": "node_ids"},
        },
        {
            "fact": "probe.target",
            "value_type": "endpoint",
            "resolver": "compose_endpoint",
            "options": {"host_field": "host", "port_field": "port"},
        },
    ])

    facts = InstanceFactResolver.resolve(
        plugin,
        {"host": "2001:db8::1", "port": 443, "node_ids": ["n1"]},
        {"nodes": [{"id": "n1", "name": "北京节点", "ip": "10.0.0.1"}]},
    )

    assert facts == {
        "collector.nodes": [{"id": "n1", "name": "北京节点", "ip": "10.0.0.1"}],
        "probe.target": "[2001:db8::1]:443",
    }


def test_binding_rejects_sensitive_input_and_unknown_resolver():
    with pytest.raises(BaseAppException, match="敏感字段"):
        InstanceFactResolver.validate_bindings([{
            "fact": "asset.secret",
            "value_type": "text",
            "resolver": "input",
            "options": {"field": "ENV_PASSWORD"},
        }])

    with pytest.raises(BaseAppException, match="不支持的 resolver"):
        InstanceFactResolver.validate_bindings([{
            "fact": "asset.ip",
            "value_type": "ip",
            "resolver": "guess",
        }])


def test_required_ip_fact_rejects_non_ip_value():
    plugin = _plugin([{
        "fact": "asset.ip",
        "value_type": "ip",
        "resolver": "input",
        "options": {"field": "host", "required": True},
    }])

    with pytest.raises(BaseAppException, match="必需实例事实无法规整"):
        InstanceFactResolver.resolve(plugin, {"host": "host.example.com"})


def test_required_selected_node_fact_rejects_missing_node_field():
    plugin = _plugin([{
        "fact": "asset.ip",
        "value_type": "ip",
        "resolver": "selected_node",
        "options": {"selection_field": "node_ids", "node_field": "ip", "required": True},
    }])

    with pytest.raises(BaseAppException, match="必需实例事实缺失"):
        InstanceFactResolver.resolve(
            plugin,
            {"node_ids": ["node-1"]},
            {"nodes": [{"id": "node-1", "name": "fusion-collector"}]},
        )

def test_merge_rejects_conflicting_single_fact():
    with pytest.raises(BaseAppException, match="实例事实冲突"):
        InstanceFactResolver.merge({"asset.ip": "10.0.0.1"}, {"asset.ip": "10.0.0.2"})


def test_same_plugin_can_update_its_fact_but_different_plugin_cannot():
    facts = InstanceFactResolver.merge({}, {"asset.ip": "10.0.0.1"}, "host-local")
    facts = InstanceFactResolver.merge(facts, {"asset.ip": "10.0.0.2"}, "host-local")
    assert facts["asset.ip"] == "10.0.0.2"

    with pytest.raises(BaseAppException, match="实例事实冲突"):
        InstanceFactResolver.merge(facts, {"asset.ip": "10.0.0.3"}, "host-remote")


def test_builtin_plugin_summary_columns_reference_declared_facts():
    plugin_root = Path(__file__).parents[1] / "support-files" / "plugins"
    critical_plugins = {"Host", "Host Remote", "Website", "Ping", "TCPPort", "Mysql", "Redis"}
    covered_plugins = set()

    for metrics_path in plugin_root.rglob("metrics.json"):
        data = json.loads(metrics_path.read_text(encoding="utf-8"))
        bindings = InstanceFactResolver.validate_bindings(data.get("instance_fact_bindings", []))
        facts = {binding["fact"] for binding in bindings}
        column_blocks = [data.get("instance_summary_columns") or []]
        if data.get("is_compound_object"):
            column_blocks.extend(obj.get("instance_summary_columns") or [] for obj in data.get("objects", []))
        for columns in column_blocks:
            for column in columns:
                assert column["fact"] in facts, f"{metrics_path}: {column['fact']} 未声明事实绑定"
        if bindings:
            covered_plugins.add(data["plugin"])

    assert critical_plugins <= covered_plugins
