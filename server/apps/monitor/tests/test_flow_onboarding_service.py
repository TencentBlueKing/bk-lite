import json
from pathlib import Path

from apps.monitor.models.monitor_object import MonitorInstance, MonitorObject


def test_flow_instance_fields_and_protocols_are_persisted(db):
    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")

    instance = MonitorInstance.objects.create(
        id="('flow-device-1',)",
        name="Flow Device 1",
        monitor_object_id=switch_object.id,
        cloud_region_id=1,
        ip="10.0.0.12",
        fallback_sampling_rate=1000,
        enabled_protocols=["netflow"],
    )

    instance.refresh_from_db()

    assert instance.cloud_region_id == 1
    assert instance.ip == "10.0.0.12"
    assert instance.fallback_sampling_rate == 1000
    assert instance.enabled_protocols == ["netflow"]

    defaulted_instance = MonitorInstance.objects.create(
        id="('flow-device-2',)",
        name="Flow Device 2",
        monitor_object_id=switch_object.id,
    )

    defaulted_instance.refresh_from_db()

    assert defaulted_instance.fallback_sampling_rate == 1000


def test_flow_plugin_seed_files_define_expected_templates():
    plugin_root = Path(__file__).resolve().parents[1] / "support-files" / "plugins" / "Telegraf"
    expected_templates = {
        ("switch", "netflow"): ("Switch", "Switch Flow NetFlow"),
        ("switch", "sflow"): ("Switch", "Switch Flow sFlow"),
        ("router", "netflow"): ("Router", "Router Flow NetFlow"),
        ("router", "sflow"): ("Router", "Router Flow sFlow"),
        ("firewall", "netflow"): ("Firewall", "Firewall Flow NetFlow"),
        ("firewall", "sflow"): ("Firewall", "Firewall Flow sFlow"),
        ("loadbalance", "netflow"): ("Loadbalance", "Loadbalance Flow NetFlow"),
        ("loadbalance", "sflow"): ("Loadbalance", "Loadbalance Flow sFlow"),
    }

    for (instance_type, protocol), (object_name, plugin_name) in expected_templates.items():
        metrics_path = plugin_root / protocol / instance_type / "metrics.json"
        policy_path = plugin_root / protocol / instance_type / "policy.json"

        assert metrics_path.exists()
        assert policy_path.exists()

        metrics = json.loads(metrics_path.read_text())
        policy = json.loads(policy_path.read_text())

        assert metrics["plugin"] == plugin_name
        assert metrics["name"] == object_name
        assert metrics["status_query"] == f"any({{instance_type='{instance_type}', collect_type='{protocol}'}}) by (instance_id)"
        assert metrics["default_metric"] == f"any({{instance_type='{instance_type}'}}) by (instance_id)"
        assert metrics["metrics"]
        assert policy["plugin"] == plugin_name
        assert policy["object"] == object_name
