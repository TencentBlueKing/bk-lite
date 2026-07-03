"""Contract tests for the TsnTec switch SNMP plugin.

TsnTec 8148SC switches expose vendor health OIDs under PEN 65531. The current
evidence confirms CPU usage, memory usage, CPU/FPGA/switch-chip temperatures,
fan status, power status and IF-MIB/ifXTable support. The plugin follows the
current SNMP brand-child contract: metrics.json declares only vendor delta
health metrics, while the shared Switch SNMP floor supplies uptime, IF-MIB
interface metrics, 64-bit HC traffic counters and device traffic roll-ups.
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
BRAND_DIR = PLUGINS / "snmp" / "switch_tsntec"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "tsntec"
COLLECT_TYPE = "snmp_tsntec"
CONFIG_TYPE = "tsntec"
INSTANCE_TYPE = "switch"
PLUGIN_NAME = "Switch TsnTec SNMP"
OBJECT_NAME = "Switch"
PEN_ROOT = "1.3.6.1.4.1.65531"

BASE_METRICS = {
    "snmp_uptime",
    "interface_ifAdminStatus",
    "interface_ifOperStatus",
    "interface_ifSpeed",
    "interface_ifInErrors",
    "interface_ifOutErrors",
    "interface_ifInDiscards",
    "interface_ifOutDiscards",
    "interface_ifInUcastPkts",
    "interface_ifOutUcastPkts",
    "interface_ifInOctets",
    "interface_ifOutOctets",
    "interface_ifHCInOctets",
    "interface_ifHCOutOctets",
    "device_total_incoming_traffic",
    "device_total_outgoing_traffic",
}
VENDOR_METRICS = {
    "device_cpu_usage",
    "device_memory_usage",
    "device_temperature_celsius",
    "device_fan_state",
    "device_psu_state",
}
SUPPORTED_SCALAR_UNITS = {
    "byteps",
    "bytes",
    "bitps",
    "counts",
    "cps",
    "percent",
    "celsius",
    "s",
    "short",
    "none",
}


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
    assert 'instance_type = "{{ instance_type }}"' in toml_text
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
def test_metrics_json_declares_only_vendor_delta(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    assert names == VENDOR_METRICS
    assert sorted(names & BASE_METRICS) == []
    assert sorted(metrics["supplementary_indicators"]) == sorted(VENDOR_METRICS)


@pytest.mark.unit
def test_cpu_memory_and_temperature_metric_contract(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    assert by["device_cpu_usage"]["unit"] == "percent"
    assert by["device_cpu_usage"]["metric_group"] == "CPU"
    assert by["device_cpu_usage"]["query"].startswith("max(")

    assert by["device_memory_usage"]["unit"] == "percent"
    assert by["device_memory_usage"]["metric_group"] == "Memory"
    assert by["device_memory_usage"]["query"].startswith("max(")
    assert "device_memory_used" not in by
    assert "device_memory_free" not in by

    assert by["device_temperature_celsius"]["unit"] == "celsius"
    assert by["device_temperature_celsius"]["metric_group"] == "Temperature"
    assert by["device_temperature_celsius"]["query"].startswith("max(")


@pytest.mark.unit
def test_hardware_state_metrics_are_enums(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    for name in ("device_fan_state", "device_psu_state"):
        metric = by[name]
        assert metric["metric_group"] == "Hardware Status"
        assert metric["data_type"] == "Enum"
        ids = {opt["id"] for opt in json.loads(metric["unit"])}
        assert ids == {1, 2}
        assert metric["query"].startswith("max(")


@pytest.mark.unit
def test_toml_uses_tsntec_private_pen_and_health_oids(toml_text):
    assert PEN_ROOT in toml_text
    for oid in (
        f"{PEN_ROOT}.1.25",
        f"{PEN_ROOT}.1.26",
        f"{PEN_ROOT}.1.7",
        f"{PEN_ROOT}.1.10",
        f"{PEN_ROOT}.1.19",
    ):
        assert oid in toml_text


@pytest.mark.unit
def test_toml_collects_64bit_ifhc_counters(toml_text):
    assert "1.3.6.1.2.1.31.1.1.1.6" in toml_text
    assert "1.3.6.1.2.1.31.1.1.1.10" in toml_text
    assert "ifHCInOctets" in toml_text and "ifHCOutOctets" in toml_text


@pytest.mark.unit
def test_toml_collects_iftable_and_uptime(toml_text):
    assert "1.3.6.1.2.1.1.3.0" in toml_text
    assert "1.3.6.1.2.1.2.2" in toml_text


@pytest.mark.unit
def test_enum_processor_normalizes_fan_and_psu_to_1_normal_2_fault(toml_text):
    assert "[[processors.enum]]" in toml_text
    assert 'namepass = ["device_fan"]' in toml_text
    assert 'namepass = ["device_psu"]' in toml_text
    assert toml_text.count("default = 2") >= 2
    assert toml_text.count('"1" = 1') >= 2


@pytest.mark.unit
def test_all_scalar_metric_units_supported(metrics):
    bad = [
        f'{m["name"]}:{m["unit"]}'
        for m in metrics["metrics"]
        if m["data_type"] != "Enum" and m["unit"] not in SUPPORTED_SCALAR_UNITS
    ]
    assert bad == []


@pytest.mark.unit
def test_policy_templates_reference_existing_metrics(metrics, policy):
    known = {m["name"] for m in metrics["metrics"]}
    bad = [t["metric_name"] for t in policy["templates"] if t["metric_name"] not in known]
    assert bad == []


@pytest.mark.unit
def test_policy_covers_vendor_health_metrics(policy):
    names = {t["metric_name"] for t in policy["templates"]}
    assert names == VENDOR_METRICS


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
def test_frontend_collecttype_wired_to_switch_object():
    switch_tsx = (
        WEB_ROOT / "src" / "app" / "monitor" / "hooks" / "integration"
        / "objects" / "networkDevice" / "switch.tsx"
    )
    text = switch_tsx.read_text(encoding="utf-8")
    assert f"'{PLUGIN_NAME}': '{COLLECT_TYPE}'" in text


@pytest.mark.unit
def test_brand_match_present_in_common():
    common = WEB_ROOT / "src" / "app" / "monitor" / "utils" / "common.tsx"
    text = common.read_text(encoding="utf-8")
    assert BRAND in text
    assert "mm-tsntec_tsntec" in text


@pytest.mark.unit
def test_passwords_use_template_vars_not_plaintext(toml_text):
    assert 'auth_password = "${AUTH_PASSWORD__{{ config_id }}}"' in toml_text
    assert 'priv_password = "${PRIV_PASSWORD__{{ config_id }}}"' in toml_text
    assert 'auth_password = "{{ auth_password }}"' not in toml_text
    assert 'priv_password = "{{ priv_password }}"' not in toml_text


@pytest.mark.unit
def test_ui_password_fields_use_secret_env_names(ui):
    field_names = {field["name"] for field in ui["form_fields"]}
    assert "ENV_AUTH_PASSWORD" in field_names
    assert "ENV_PRIV_PASSWORD" in field_names
    assert "auth_password" not in field_names
    assert "priv_password" not in field_names
