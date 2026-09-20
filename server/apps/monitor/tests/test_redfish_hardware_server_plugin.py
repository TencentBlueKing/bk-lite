import json
from pathlib import Path

import pytest
import yaml
from jinja2 import Template

PLUGIN_DIR = Path(__file__).resolve().parents[1] / "support-files" / "plugins" / "Telegraf" / "redfish" / "hardware_server"

ADDED_METRICS = [
    "redfish_inlet_temperature_celsius",
    "redfish_inlet_temperature_upper_critical_celsius",
    "redfish_psu_output_watts",
    "redfish_psu_capacity_watts",
    "redfish_psu_delivering",
    "redfish_psu_redundant",
    "redfish_power_limit_watts",
    "redfish_power_over_limit",
    "redfish_drive_health",
    "redfish_drive_present_count",
    "redfish_drive_life_percent",
]


@pytest.fixture(scope="module")
def metrics():
    return json.loads((PLUGIN_DIR / "metrics.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def policy():
    return json.loads((PLUGIN_DIR / "policy.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module", params=["zh-Hans.yaml", "en.yaml"])
def language(request):
    return yaml.safe_load((PLUGIN_DIR / "language" / request.param).read_text(encoding="utf-8"))


@pytest.mark.unit
def test_template_scrapes_stargazer_redfish_metrics():
    rendered = Template((PLUGIN_DIR / "hardware_server.child.toml.j2").read_text(encoding="utf-8")).render(
        ip="192.0.2.10",
        username="ro",
        config_id="cfg_1",
        instance_id="server_1",
        instance_type="hardware_server",
        interval=60,
    )

    assert "/api/monitor/redfish/metrics" in rendered
    assert 'verify_tls = "{{ verify_tls | default(true) | lower }}"' in (PLUGIN_DIR / "hardware_server.child.toml.j2").read_text(encoding="utf-8")


@pytest.mark.unit
def test_manifest_registers_power_disk_and_inlet_metrics(metrics):
    names = [metric["name"] for metric in metrics["metrics"]]

    for name in ADDED_METRICS:
        assert name in names
    assert "redfish_sel_" not in "".join(names)
    assert metrics["supplementary_indicators"] == [
        "redfish_system_health",
        "redfish_system_power_state",
        "redfish_inlet_temperature_celsius",
        "redfish_psu_redundant",
        "redfish_drive_health",
    ]


@pytest.mark.unit
def test_added_metrics_have_translations(metrics, language):
    metric_translations = language["monitor_object_metric"]["Hardware Server"]
    group_translations = language["monitor_object_metric_group"]["Hardware Server"]

    for metric in metrics["metrics"]:
        assert metric["name"] in metric_translations
        assert metric["metric_group"] in group_translations


@pytest.mark.unit
def test_policy_uses_first_class_inlet_power_and_drive_metrics(policy):
    by_name = {item["name"]: item["metric_name"] for item in policy["templates"]}

    assert by_name["进风口温度过高"] == "redfish_inlet_temperature_celsius"
    assert by_name["电源冗余丢失"] == "redfish_psu_redundant"
    assert by_name["功耗超限"] == "redfish_power_over_limit"
    assert by_name["磁盘健康异常"] == "redfish_drive_health"
