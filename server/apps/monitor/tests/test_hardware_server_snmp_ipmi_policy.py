import json
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1] / "support-files" / "plugins" / "Telegraf"
SNMP_POLICY = PLUGIN_ROOT / "snmp" / "hardware_server" / "policy.json"
IPMI_POLICY = PLUGIN_ROOT / "ipmi" / "hardware_server" / "policy.json"
IPMI_METRICS = PLUGIN_ROOT / "ipmi" / "hardware_server" / "metrics.json"
IPMI_METRIC_NAMES = {
    "ipmi_power_watts",
    "ipmi_voltage_volts",
    "ipmi_fan_speed_rpm",
    "ipmi_temperature_celsius",
    "ipmi_chassis_power_state",
}


def test_hardware_server_snmp_policy_does_not_reference_ipmi_metrics():
    payload = json.loads(SNMP_POLICY.read_text(encoding="utf-8"))
    assert payload["plugin"] == "Hardware Server SNMP General"
    names = {item["metric_name"] for item in payload["templates"]}
    assert names.isdisjoint(IPMI_METRIC_NAMES)


def test_hardware_server_ipmi_policy_owns_ipmi_metrics():
    payload = json.loads(IPMI_POLICY.read_text(encoding="utf-8"))
    metrics = json.loads(IPMI_METRICS.read_text(encoding="utf-8"))
    assert payload["plugin"] == "Hardware Server IPMI"
    names = {item["metric_name"] for item in payload["templates"]}
    catalog = {item["name"] for item in metrics["metrics"]}
    assert names == IPMI_METRIC_NAMES
    assert names <= catalog
