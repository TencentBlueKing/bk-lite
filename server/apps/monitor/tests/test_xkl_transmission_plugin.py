"""Contract tests for the XKL DXMOS transmission SNMP plugin.

XKL DXMOS optical transport systems expose hardware health objects in XKL-MIB
under enterprise PEN 21150:
  - xklSensorTemp              1.3.6.1.4.1.21150.1.1.13.1.3, degrees Celsius
  - xklFanControllerStatus     1.3.6.1.4.1.21150.1.1.5.1.2, normal(2)
  - xklPowerStatus             1.3.6.1.4.1.21150.1.1.9.1.2, normal(2)

Uptime and IF-MIB interface traffic are collected by the child TOML but are
supplied to capabilities by the shared Transmission SNMP floor, so metrics.json
stays a vendor-specific delta child.
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
BRAND_DIR = PLUGINS / "snmp" / "transmission_xkl"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "xkl"
COLLECT_TYPE = "snmp_xkl"
CONFIG_TYPE = "xkl"
INSTANCE_TYPE = "transmission"
PLUGIN_NAME = "Transmission XKL SNMP"
OBJECT_NAME = "Transmission"
PEN_ROOT = "1.3.6.1.4.1.21150"
SENSOR_TEMP_OID = "1.3.6.1.4.1.21150.1.1.13.1.3"
FAN_STATUS_OID = "1.3.6.1.4.1.21150.1.1.5.1.2"
POWER_STATUS_OID = "1.3.6.1.4.1.21150.1.1.9.1.2"

EXPECTED_METRICS = {
    "device_temperature_celsius",
    "device_fan_state",
    "device_psu_state",
}
ABSENT_METRICS = (
    "snmp_uptime", "interface_ifHCInOctets", "interface_ifHCOutOctets",
    "device_total_incoming_traffic", "device_total_outgoing_traffic",
    "device_cpu_usage", "device_memory_usage", "device_memory_total",
    "device_memory_free", "device_memory_used",
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
def test_plugin_lives_under_correct_dir(metrics):
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
def test_ui_is_pure_snmp_form(ui):
    assert not any(f["name"] == "brand" for f in ui["form_fields"])


@pytest.mark.unit
def test_metrics_is_vendor_delta_child(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    assert names == EXPECTED_METRICS
    assert all(name not in names for name in ABSENT_METRICS)
    assert sorted(metrics["supplementary_indicators"]) == sorted(EXPECTED_METRICS)


@pytest.mark.unit
def test_temperature_fan_and_power_metric_contract(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    assert by["device_temperature_celsius"]["unit"] == "celsius"
    assert by["device_temperature_celsius"]["metric_group"] == "Temperature"
    assert by["device_temperature_celsius"]["query"].startswith("max(")

    for name in ("device_fan_state", "device_psu_state"):
        metric = by[name]
        assert metric["metric_group"] == "Hardware Status"
        assert metric["data_type"] == "Enum"
        assert {opt["id"] for opt in json.loads(metric["unit"])} == {1, 2}
        assert metric["query"].startswith("max(")


@pytest.mark.unit
def test_cpu_and_memory_not_modelled(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    assert "device_cpu_usage" not in names
    assert "device_memory_usage" not in names


@pytest.mark.unit
def test_private_oids_under_pen_21150(toml_text):
    assert PEN_ROOT in toml_text
    assert SENSOR_TEMP_OID in toml_text
    assert FAN_STATUS_OID in toml_text
    assert POWER_STATUS_OID in toml_text


@pytest.mark.unit
def test_temperature_oid_has_no_scaling(toml_text, metrics):
    assert "/10" not in toml_text
    assert "/100" not in toml_text
    query = {m["name"]: m["query"] for m in metrics["metrics"]}["device_temperature_celsius"]
    assert "/10" not in query and "/100" not in query


@pytest.mark.unit
def test_enum_processor_normalizes_normal_2_to_1(toml_text):
    assert "[[processors.enum]]" in toml_text
    assert 'namepass = ["device_fan"]' in toml_text
    assert 'namepass = ["device_psu"]' in toml_text
    assert toml_text.count("default = 2") >= 2
    assert toml_text.count('"2" = 1') >= 2


@pytest.mark.unit
def test_toml_collects_64bit_ifhc_counters(toml_text):
    assert "1.3.6.1.2.1.31.1.1.1.6" in toml_text
    assert "1.3.6.1.2.1.31.1.1.1.10" in toml_text
    assert "ifHCInOctets" in toml_text and "ifHCOutOctets" in toml_text


@pytest.mark.unit
def test_toml_collects_uptime(toml_text):
    assert "1.3.6.1.2.1.1.3.0" in toml_text


@pytest.mark.unit
def test_policy_templates_reference_existing_metrics(metrics, policy):
    known = {m["name"] for m in metrics["metrics"]}
    bad = [t["metric_name"] for t in policy["templates"] if t["metric_name"] not in known]
    assert bad == []


@pytest.mark.unit
def test_policy_covers_health_metrics(policy):
    assert {t["metric_name"] for t in policy["templates"]} == EXPECTED_METRICS


@pytest.mark.unit
def test_plugin_has_bilingual_name_and_desc(languages):
    for lang, data in languages.items():
        entry = (data.get("monitor_object_plugin") or {}).get(PLUGIN_NAME) or {}
        assert entry.get("name"), f"{lang}: plugin name missing"
        assert entry.get("desc"), f"{lang}: plugin desc missing"


@pytest.mark.unit
def test_english_plugin_desc_has_no_colon_space(languages):
    desc = languages["en"]["monitor_object_plugin"][PLUGIN_NAME]["desc"]
    assert ": " not in desc


@pytest.mark.unit
def test_every_metric_has_bilingual_translation(metrics, languages):
    missing = []
    for lang, data in languages.items():
        group = (data.get("monitor_object_metric") or {}).get(OBJECT_NAME) or {}
        for metric in metrics["metrics"]:
            entry = group.get(metric["name"]) or {}
            if not entry.get("name") or not entry.get("desc"):
                missing.append(f'{lang}:{metric["name"]}')
    assert missing == []


@pytest.mark.unit
def test_metric_groups_translated(languages):
    for lang, data in languages.items():
        groups = (data.get("monitor_object_metric_group") or {}).get(OBJECT_NAME) or {}
        for group in ("Temperature", "Hardware Status"):
            assert group in groups, f"{lang}: metric group missing {group}"


@pytest.mark.unit
def test_frontend_collecttype_wired_to_transmission_object():
    tsx = (
        WEB_ROOT / "src" / "app" / "monitor" / "hooks" / "integration"
        / "objects" / "networkDevice" / "transmission.tsx"
    )
    assert f"'{PLUGIN_NAME}': '{COLLECT_TYPE}'" in tsx.read_text(encoding="utf-8")


@pytest.mark.unit
def test_frontend_brand_match_registered():
    common = WEB_ROOT / "src" / "app" / "monitor" / "utils" / "common.tsx"
    text = common.read_text(encoding="utf-8").lower()
    assert "xkl" in text
    assert "dxmos" in text


@pytest.mark.unit
def test_brand_icon_asset_present():
    icon = WEB_ROOT / "public" / "assets" / "icons" / "mm-xkl_xkl.svg"
    assert icon.exists()


@pytest.mark.unit
def test_passwords_use_sidecar_env_placeholders_not_plaintext(ui, toml_text):
    field_names = {field["name"] for field in ui["form_fields"]}
    assert "ENV_AUTH_PASSWORD" in field_names
    assert "ENV_PRIV_PASSWORD" in field_names
    assert 'auth_password = "${AUTH_PASSWORD__{{ config_id }}}"' in toml_text
    assert 'priv_password = "${PRIV_PASSWORD__{{ config_id }}}"' in toml_text
    assert 'auth_password = "{{ auth_password }}"' not in toml_text
    assert 'priv_password = "{{ priv_password }}"' not in toml_text
