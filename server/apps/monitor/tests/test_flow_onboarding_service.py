import json
from pathlib import Path

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models.monitor_metrics import Metric
from apps.monitor.models.monitor_object import MonitorInstance, MonitorInstanceOrganization, MonitorObject
from apps.monitor.services.flow_onboarding import FlowOnboardingService
from apps.monitor.services.plugin import MonitorPluginService


PLUGIN_ROOT = Path(__file__).resolve().parents[1] / "support-files" / "plugins" / "Telegraf"


def _load_plugin_seed(protocol: str, instance_type: str, file_name: str):
    return json.loads((PLUGIN_ROOT / protocol / instance_type / file_name).read_text())


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


def test_create_or_bind_flow_asset_reuses_existing_instance(db):
    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")
    existing = MonitorInstance.objects.create(
        id="('flow-device-1',)",
        name="Core Switch",
        monitor_object_id=switch_object.id,
        cloud_region_id=1,
        ip="10.0.0.12",
        fallback_sampling_rate=1000,
        enabled_protocols=["netflow"],
    )

    result = FlowOnboardingService.create_or_bind_asset(
        monitor_object_id=switch_object.id,
        protocol="sflow",
        cloud_region_id=1,
        ip="10.0.0.12",
        name="Core Switch",
        organizations=[1],
        instance_id=existing.id,
    )

    existing.refresh_from_db()
    assert result["instance_id"] == existing.id
    assert set(existing.enabled_protocols) == {"netflow", "sflow"}


def test_create_or_bind_flow_asset_creates_monitor_side_asset(db):
    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")

    result = FlowOnboardingService.create_or_bind_asset(
        monitor_object_id=switch_object.id,
        protocol="netflow",
        cloud_region_id=1,
        ip="10.0.0.12",
        name="Core Switch",
        organizations=[1, 2],
        fallback_sampling_rate=2000,
    )

    instance = MonitorInstance.objects.get(id=result["instance_id"])
    assert instance.monitor_object_id == switch_object.id
    assert instance.name == "Core Switch"
    assert instance.cloud_region_id == 1
    assert instance.ip == "10.0.0.12"
    assert instance.fallback_sampling_rate == 2000
    assert instance.enabled_protocols == ["netflow"]
    assert instance.auto is False
    assert set(
        MonitorInstanceOrganization.objects.filter(monitor_instance_id=instance.id).values_list("organization", flat=True)
    ) == {1, 2}


def test_update_flow_asset_updates_editable_fields(db):
    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")
    instance = MonitorInstance.objects.create(
        id="('flow-device-1',)",
        name="Core Switch",
        monitor_object_id=switch_object.id,
        cloud_region_id=1,
        ip="10.0.0.12",
        fallback_sampling_rate=1000,
        enabled_protocols=["netflow", "sflow"],
    )
    MonitorInstanceOrganization.objects.create(monitor_instance_id=instance.id, organization=1)

    result = FlowOnboardingService.update_asset(
        instance_id=instance.id,
        name="Core Switch Updated",
        organizations=[2],
        cloud_region_id=2,
        ip="10.0.0.13",
        fallback_sampling_rate=3000,
    )

    instance.refresh_from_db()
    assert result["instance_id"] == instance.id
    assert instance.name == "Core Switch Updated"
    assert instance.cloud_region_id == 2
    assert instance.ip == "10.0.0.13"
    assert instance.fallback_sampling_rate == 3000
    assert set(instance.enabled_protocols) == {"netflow", "sflow"}
    assert set(
        MonitorInstanceOrganization.objects.filter(monitor_instance_id=instance.id).values_list("organization", flat=True)
    ) == {2}


def test_create_or_bind_flow_asset_rejects_unknown_protocol(db):
    switch_object = MonitorObject.objects.create(name="Switch", display_name="Switch")

    with pytest.raises(BaseAppException, match="Unsupported flow protocol"):
        FlowOnboardingService.create_or_bind_asset(
            monitor_object_id=switch_object.id,
            protocol="ipfix",
            cloud_region_id=1,
            ip="10.0.0.12",
            name="Core Switch",
            organizations=[1],
        )


def test_flow_plugin_seed_files_define_expected_templates():
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
        metrics_path = PLUGIN_ROOT / protocol / instance_type / "metrics.json"
        policy_path = PLUGIN_ROOT / protocol / instance_type / "policy.json"

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


def test_flow_plugin_seed_files_use_protocol_specific_metric_names():
    for instance_type in ("switch", "router", "firewall", "loadbalance"):
        snmp_metric_names = {
            metric["name"] for metric in _load_plugin_seed("snmp", instance_type, "metrics.json")["metrics"]
        }

        for protocol in ("netflow", "sflow"):
            metrics = _load_plugin_seed(protocol, instance_type, "metrics.json")
            policy = _load_plugin_seed(protocol, instance_type, "policy.json")
            expected_names = [
                f"device_total_incoming_{protocol}_traffic",
                f"device_total_outgoing_{protocol}_traffic",
            ]

            assert metrics["supplementary_indicators"] == expected_names
            assert [metric["name"] for metric in metrics["metrics"]] == expected_names
            assert [template["metric_name"] for template in policy["templates"]] == expected_names
            assert snmp_metric_names.isdisjoint(expected_names)


def test_flow_plugin_import_keeps_metric_name_queries_unambiguous(db):
    MonitorPluginService.import_monitor_plugin(_load_plugin_seed("snmp", "switch", "metrics.json"))
    MonitorPluginService.import_monitor_plugin(_load_plugin_seed("netflow", "switch", "metrics.json"))
    MonitorPluginService.import_monitor_plugin(_load_plugin_seed("sflow", "switch", "metrics.json"))

    switch_object = MonitorObject.objects.get(name="Switch")

    snmp_metric = Metric.objects.get(monitor_object=switch_object, name="device_total_incoming_traffic")
    netflow_metric = Metric.objects.get(monitor_object=switch_object, name="device_total_incoming_netflow_traffic")
    sflow_metric = Metric.objects.get(monitor_object=switch_object, name="device_total_incoming_sflow_traffic")

    assert snmp_metric.monitor_plugin_id != netflow_metric.monitor_plugin_id
    assert netflow_metric.monitor_plugin_id != sflow_metric.monitor_plugin_id
    assert Metric.objects.filter(monitor_object=switch_object, name="device_total_incoming_traffic").count() == 1
    assert Metric.objects.filter(monitor_object=switch_object, name="device_total_incoming_netflow_traffic").count() == 1
    assert Metric.objects.filter(monitor_object=switch_object, name="device_total_incoming_sflow_traffic").count() == 1
