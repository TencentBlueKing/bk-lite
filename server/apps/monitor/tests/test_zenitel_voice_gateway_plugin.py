"""Contract tests for the Zenitel voice gateway SNMP plugin.

Zenitel Vingtor-Stentofon Exigo and Turbine devices expose VS-DEVICE-MIB
temperature and power-source status tables under PEN 26122. Fan is RPM-only and
voltage is mV-only, so this plugin keeps them out of shared state metrics.
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
BRAND_DIR = PLUGINS / "snmp" / "voice_gateway_zenitel"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "zenitel"
COLLECT_TYPE = "snmp_zenitel"
CONFIG_TYPE = "zenitel"
INSTANCE_TYPE = "voice_gateway"
PLUGIN_NAME = "VoiceGateway Zenitel SNMP"
OBJECT_NAME = "VoiceGateway"

BASE_METRICS = (
    "snmp_uptime",
    "interface_ifHCInOctets",
    "interface_ifHCOutOctets",
    "device_total_incoming_traffic",
    "device_total_outgoing_traffic",
)
EXPECTED_METRICS = {
    "device_temperature_celsius",
    "device_psu_state",
}
UNSUPPORTED_HEALTH_METRICS = (
    "device_cpu_usage",
    "device_memory_usage",
    "device_memory_used",
    "device_memory_free",
    "device_fan_state",
    "device_fan_speed",
    "device_voltage_volts",
    "device_psu_state",
    "device_disk_state",
    "device_raid_state",
)


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def metrics():
    return _read_json(BRAND_DIR / "metrics.json")


@pytest.fixture(scope="module")
def policy():
    return _read_json(BRAND_DIR / "policy.json")


@pytest.fixture(scope="module")
def ui():
    return _read_json(BRAND_DIR / "UI.json")


@pytest.fixture(scope="module")
def toml_text():
    return (BRAND_DIR / f"{CONFIG_TYPE}.child.toml.j2").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def languages():
    return {
        lang: yaml.safe_load((LANGUAGE_DIR / f"{lang}.yaml").read_text(encoding="utf-8"))
        for lang in ("zh-Hans", "en")
    }


@pytest.mark.unit
def test_plugin_lives_under_snmp_dir(metrics):
    assert metrics["collect_type"] == COLLECT_TYPE
    assert BRAND_DIR.parent.name == "snmp"


@pytest.mark.unit
def test_toml_filename_follows_convention():
    assert (BRAND_DIR / f"{CONFIG_TYPE}.child.toml.j2").exists()


@pytest.mark.unit
def test_collect_type_consistent_across_files(metrics, policy, ui, toml_text):
    assert COLLECT_TYPE in metrics["status_query"]
    assert f"instance_type='{INSTANCE_TYPE}'" in metrics["status_query"]
    assert ui["collect_type"] == COLLECT_TYPE
    assert f'collect_type = "{COLLECT_TYPE}"' in toml_text
    assert metrics["plugin"] == PLUGIN_NAME
    assert policy["plugin"] == PLUGIN_NAME
    assert metrics["name"] == OBJECT_NAME
    assert ui["object_name"] == OBJECT_NAME
    assert policy["object"] == OBJECT_NAME


@pytest.mark.unit
def test_config_type_consistent(ui, toml_text):
    assert ui["config_type"] == [CONFIG_TYPE]
    assert f'config_type = "{CONFIG_TYPE}"' in toml_text
    assert f'brand = "{BRAND}"' in toml_text


@pytest.mark.unit
def test_ui_is_pure_snmp_form_with_sidecar_secret_fields(ui):
    fields = {field["name"] for field in ui["form_fields"]}
    assert "brand" not in fields
    assert "ENV_AUTH_PASSWORD" in fields
    assert "ENV_PRIV_PASSWORD" in fields
    assert "auth_password" not in fields
    assert "priv_password" not in fields


@pytest.mark.unit
def test_snmpv3_passwords_use_runtime_env_placeholders(toml_text):
    assert "${AUTH_PASSWORD__{{ config_id }}}" in toml_text
    assert "${PRIV_PASSWORD__{{ config_id }}}" in toml_text
    assert "{{ auth_password }}" not in toml_text
    assert "{{ priv_password }}" not in toml_text


@pytest.mark.unit
def test_only_verified_private_health_oids_are_modelled(metrics, toml_text):
    names = {m["name"] for m in metrics["metrics"]}
    assert names == EXPECTED_METRICS
    for absent in set(UNSUPPORTED_HEALTH_METRICS) - EXPECTED_METRICS:
        assert absent not in names
        assert absent not in toml_text
    assert "1.3.6.1.4.1.26122.3.2.2.1.4" in toml_text
    assert "1.3.6.1.4.1.26122.3.5.1.1.5" in toml_text


@pytest.mark.unit
def test_metrics_json_declares_only_vendor_delta_child(metrics):
    assert set(metrics["supplementary_indicators"]) == EXPECTED_METRICS
    names = {m["name"] for m in metrics["metrics"]}
    assert [name for name in BASE_METRICS if name in names] == []


@pytest.mark.unit
def test_policy_templates_reference_existing_metrics(metrics, policy):
    known = {m["name"] for m in metrics["metrics"]}
    bad = [t["metric_name"] for t in policy["templates"] if t["metric_name"] not in known]
    assert bad == []


@pytest.mark.unit
def test_toml_collects_uptime_and_64bit_ifhc_counters(toml_text):
    assert "1.3.6.1.2.1.1.3.0" in toml_text
    assert "1.3.6.1.2.1.31.1.1.1.6" in toml_text
    assert "1.3.6.1.2.1.31.1.1.1.10" in toml_text
    assert "1.3.6.1.2.1.2.2.1.10" not in toml_text
    assert "1.3.6.1.2.1.2.2.1.16" not in toml_text


@pytest.mark.unit
def test_temperature_and_power_metrics_are_grouped(metrics):
    by_name = {m["name"]: m for m in metrics["metrics"]}
    temp = by_name["device_temperature_celsius"]
    assert temp["metric_group"] == "Temperature"
    assert temp["unit"] == "celsius"
    assert temp["data_type"] == "Number"
    assert temp["query"].replace(" ", "").startswith("max(")
    assert "by(instance_id)" in temp["query"].replace(" ", "")
    psu = by_name["device_psu_state"]
    assert psu["metric_group"] == "Hardware Status"
    assert psu["data_type"] == "Enum"
    assert '"id":1' in psu["unit"]
    assert '"id":2' in psu["unit"]


@pytest.mark.unit
def test_psu_enum_normalizes_connected_only_as_healthy(toml_text):
    assert "processors.enum" in toml_text
    assert 'field = "state"' in toml_text
    assert "default = 2" in toml_text
    assert '"3" = 1' in toml_text
    assert '"1" = 1' not in toml_text
    assert '"2" = 1' not in toml_text


@pytest.mark.unit
def test_fan_rpm_and_voltage_are_not_promoted(metrics, toml_text):
    names = {m["name"] for m in metrics["metrics"]}
    assert "device_fan_state" not in names
    assert "device_fan_speed" not in names
    assert "device_voltage_volts" not in names
    assert "1.3.6.1.4.1.26122.3.3.2.1.3" not in toml_text
    assert "1.3.6.1.4.1.26122.3.4.2.1.3" not in toml_text


@pytest.mark.unit
def test_plugin_has_bilingual_name_and_desc(languages):
    for lang, data in languages.items():
        entry = (data.get("monitor_object_plugin") or {}).get(PLUGIN_NAME) or {}
        assert entry.get("name"), f"{lang}: plugin name missing"
        assert entry.get("desc"), f"{lang}: plugin desc missing"


@pytest.mark.unit
def test_en_desc_has_no_halfwidth_colon_space(languages):
    en = (languages["en"].get("monitor_object_plugin") or {}).get(PLUGIN_NAME) or {}
    assert ": " not in en.get("desc", "")


@pytest.mark.unit
def test_frontend_collecttype_wired_to_voice_gateway_object():
    tsx = (
        WEB_ROOT / "src" / "app" / "monitor" / "hooks" / "integration"
        / "objects" / "networkDevice" / "voiceGateway.tsx"
    )
    assert f"'{PLUGIN_NAME}': '{COLLECT_TYPE}'" in tsx.read_text(encoding="utf-8")


@pytest.mark.unit
def test_brand_label_present_in_common():
    common = WEB_ROOT / "src" / "app" / "monitor" / "utils" / "common.tsx"
    text = common.read_text(encoding="utf-8")
    assert "Zenitel" in text
    assert "mm-zenitel_zenitel" in text
    assert "{ match: /zenitel|vingtor|stentofon/i, label: 'Zenitel'" in text
    assert "zenitel|voice" not in text.lower()
    assert "gateway|zenitel" not in text.lower()
    assert "intercom|zenitel" not in text.lower()


@pytest.mark.unit
def test_brand_svg_exists():
    assert (WEB_ROOT / "public" / "assets" / "icons" / "mm-zenitel_zenitel.svg").exists()


@pytest.mark.unit
def test_brand_files_have_no_external_source_residue():
    forbidden = [
        "Data" + "dog",
        "Libre" + "NMS",
        "Zab" + "bix",
        "Check" + "mk",
        "Open" + "NMS",
        "snmp_" + "exporter",
        "Observ" + "ium",
        "Solar" + "Winds",
        "Manage" + "Engine",
        "Net" + "Box",
    ]
    paths = list(BRAND_DIR.glob("*")) + [
        WEB_ROOT / "public" / "assets" / "icons" / "mm-zenitel_zenitel.svg"
    ]
    offenders = {
        path.name: [word for word in forbidden if word in path.read_text(encoding="utf-8")]
        for path in paths
        if path.is_file()
    }
    offenders = {name: words for name, words in offenders.items() if words}
    assert offenders == {}
