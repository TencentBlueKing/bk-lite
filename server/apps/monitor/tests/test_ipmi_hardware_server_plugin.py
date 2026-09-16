import json
from pathlib import Path

import pytest
import tomllib
import yaml
from jinja2 import Template

PLUGIN_DIR = Path(__file__).resolve().parents[1] / "support-files" / "plugins" / "Telegraf" / "ipmi" / "hardware_server"

LEGACY_METRICS = [
    "ipmi_chassis_power_state",
    "ipmi_power_watts",
    "ipmi_voltage_volts",
    "ipmi_fan_speed_rpm",
    "ipmi_temperature_celsius",
]


@pytest.fixture(scope="module")
def metrics():
    return json.loads((PLUGIN_DIR / "metrics.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def toml_text():
    return (PLUGIN_DIR / "hardware_server.child.toml.j2").read_text(encoding="utf-8")


@pytest.fixture(scope="module", params=["zh-Hans.yaml", "en.yaml"])
def language(request):
    return yaml.safe_load((PLUGIN_DIR / "language" / request.param).read_text(encoding="utf-8"))


@pytest.mark.unit
def test_template_collects_raw_ipmi_sensor_only(toml_text):
    rendered = Template(toml_text).render(
        username="monitor",
        config_id="cfg_1",
        protocol="lanplus",
        ip="192.0.2.10",
        interval=60,
        instance_id="server_1",
        instance_type="hardware_server",
    )
    parsed = tomllib.loads(rendered)

    assert list(parsed["inputs"]) == ["ipmi_sensor"]
    assert "exec" not in parsed.get("inputs", {})
    assert "processors" not in parsed
    assert "ipmi_normalizer.star" not in toml_text
    assert not (PLUGIN_DIR / "ipmi_normalizer.star").exists()


@pytest.mark.unit
def test_manifest_keeps_pre_expansion_metric_set(metrics):
    names = [metric["name"] for metric in metrics["metrics"]]

    assert names == LEGACY_METRICS
    assert metrics["metrics"][0]["query"].startswith("ipmi_sensor_status{")
    assert 'name=~"host_power"' in metrics["metrics"][0]["query"]
    assert metrics["metrics"][1]["query"].startswith("ipmi_sensor_value{")
    assert metrics["support_collect_detect"] is True


@pytest.mark.unit
def test_legacy_metrics_have_translations(metrics, language):
    metric_translations = language["monitor_object_metric"]["Hardware Server"]
    group_translations = language["monitor_object_metric_group"]["Hardware Server"]

    for metric in metrics["metrics"]:
        assert metric["name"] in metric_translations
        assert metric["metric_group"] in group_translations
    assert "Chassis" not in group_translations
    assert all(not name.startswith("ipmi_psu_") for name in metric_translations)
