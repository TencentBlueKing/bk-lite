"""Contract tests for the Wi-Tek switch SNMP plugin.

Wi-Tek managed switches expose vendor health OIDs under enterprise PEN 12284.
The plugin follows the current SNMP brand-child contract: metrics.json declares
only vendor delta health metrics, while the shared Switch SNMP floor supplies
uptime, IF-MIB interface metrics, 64-bit HC traffic counters and device traffic
roll-ups.
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
BRAND_DIR = PLUGINS / "snmp" / "switch_witek"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "witek"
COLLECT_TYPE = "snmp_witek"
CONFIG_TYPE = "witek"
INSTANCE_TYPE = "switch"
PLUGIN_NAME = "Switch Wi-Tek SNMP"
OBJECT_NAME = "Switch"
PEN_ROOT = "1.3.6.1.4.1.12284"

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
    "device_memory_used",
    "device_memory_free",
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
    assert not any(field["name"] == "brand" for field in ui["form_fields"])


@pytest.mark.unit
def test_metrics_json_declares_only_vendor_delta(metrics):
    names = {metric["name"] for metric in metrics["metrics"]}
    assert names == VENDOR_METRICS
    assert sorted(names & BASE_METRICS) == []
    assert sorted(metrics["supplementary_indicators"]) == sorted(VENDOR_METRICS)


@pytest.mark.unit
def test_cpu_memory_and_temperature_metric_contract(metrics):
    by_name = {metric["name"]: metric for metric in metrics["metrics"]}
    assert by_name["device_cpu_usage"]["unit"] == "percent"
    assert by_name["device_cpu_usage"]["metric_group"] == "CPU"
    assert by_name["device_cpu_usage"]["query"].startswith("max(")

    assert by_name["device_memory_used"]["unit"] == "bytes"
    assert by_name["device_memory_free"]["unit"] == "bytes"
    assert by_name["device_memory_usage"]["unit"] == "percent"
    assert "device_memory_used" in by_name["device_memory_usage"]["query"]
    assert "device_memory_free" in by_name["device_memory_usage"]["query"]

    assert by_name["device_temperature_celsius"]["unit"] == "celsius"
    assert by_name["device_temperature_celsius"]["metric_group"] == "Temperature"
    assert by_name["device_temperature_celsius"]["query"].startswith("max(")


@pytest.mark.unit
def test_hardware_state_metrics_are_enums(metrics):
    by_name = {metric["name"]: metric for metric in metrics["metrics"]}
    for name in ("device_fan_state", "device_psu_state"):
        metric = by_name[name]
        assert metric["metric_group"] == "Hardware Status"
        assert metric["data_type"] == "Enum"
        ids = {option["id"] for option in json.loads(metric["unit"])}
        assert ids == {1, 2}
        assert metric["query"].startswith("max(")


@pytest.mark.unit
def test_toml_uses_witek_private_pen_and_health_oids(toml_text):
    assert PEN_ROOT in toml_text
    for oid in (
        f"{PEN_ROOT}.4.2.4",
        f"{PEN_ROOT}.4.1.1",
        f"{PEN_ROOT}.4.1.4",
        f"{PEN_ROOT}.5.5.5",
        f"{PEN_ROOT}.5.5.8",
        f"{PEN_ROOT}.5.5.9",
        f"{PEN_ROOT}.5.5.22",
        f"{PEN_ROOT}.5.5.23",
    ):
        assert oid in toml_text


@pytest.mark.unit
def test_toml_does_not_collect_displaystring_industry_or_sfp_health(toml_text):
    for oid in (
        f"{PEN_ROOT}.5.6.3",
        f"{PEN_ROOT}.5.6.6",
        f"{PEN_ROOT}.5.6.17",
        f"{PEN_ROOT}.5.4.1",
    ):
        assert oid not in toml_text


@pytest.mark.unit
def test_toml_collects_64bit_ifhc_counters_only_for_traffic(toml_text):
    assert "1.3.6.1.2.1.31.1.1.1.6" in toml_text
    assert "1.3.6.1.2.1.31.1.1.1.10" in toml_text
    assert "ifHCInOctets" in toml_text and "ifHCOutOctets" in toml_text
    assert 'name = "ifInOctets"' not in toml_text
    assert 'name = "ifOutOctets"' not in toml_text
    assert 'oid = "1.3.6.1.2.1.2.2.1.10"' not in toml_text
    assert 'oid = "1.3.6.1.2.1.2.2.1.16"' not in toml_text


@pytest.mark.unit
def test_toml_collects_iftable_and_uptime(toml_text):
    assert "1.3.6.1.2.1.1.3.0" in toml_text
    assert "1.3.6.1.2.1.2.2" in toml_text
    assert "ifDescr" in toml_text


@pytest.mark.unit
def test_enum_processor_normalizes_status_to_1_normal_2_fault(toml_text):
    assert "[[processors.enum]]" in toml_text
    assert 'namepass = ["device_fan"]' in toml_text
    assert 'namepass = ["device_psu"]' in toml_text
    assert toml_text.count("default = 2") >= 4
    assert toml_text.count('"1" = 1') >= 4


@pytest.mark.unit
def test_all_scalar_metric_units_supported(metrics):
    bad = [
        f'{metric["name"]}:{metric["unit"]}'
        for metric in metrics["metrics"]
        if metric["data_type"] != "Enum" and metric["unit"] not in SUPPORTED_SCALAR_UNITS
    ]
    assert bad == []


@pytest.mark.unit
def test_policy_templates_reference_existing_metrics(metrics, policy):
    known = {metric["name"] for metric in metrics["metrics"]}
    bad = [template["metric_name"] for template in policy["templates"] if template["metric_name"] not in known]
    assert bad == []


@pytest.mark.unit
def test_policy_covers_alertable_vendor_health_metrics(policy):
    names = {template["metric_name"] for template in policy["templates"]}
    assert names == {
        "device_cpu_usage",
        "device_memory_usage",
        "device_temperature_celsius",
        "device_fan_state",
        "device_psu_state",
    }


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
def test_brand_match_and_icon_present_in_common():
    common = WEB_ROOT / "src" / "app" / "monitor" / "utils" / "common.tsx"
    text = common.read_text(encoding="utf-8")
    assert BRAND in text
    assert "mm-witek_witek" in text
    assert (WEB_ROOT / "public" / "assets" / "icons" / "mm-witek_witek.svg").exists()


@pytest.mark.unit
def test_passwords_use_sidecar_env_placeholders_not_plaintext(ui, toml_text):
    field_names = {field["name"] for field in ui["form_fields"]}
    assert "ENV_AUTH_PASSWORD" in field_names
    assert "ENV_PRIV_PASSWORD" in field_names
    assert "auth_password" not in field_names
    assert "priv_password" not in field_names
    assert 'auth_password = "${AUTH_PASSWORD__{{ config_id }}}"' in toml_text
    assert 'priv_password = "${PRIV_PASSWORD__{{ config_id }}}"' in toml_text
    assert "{{ auth_password }}" not in toml_text
    assert "{{ priv_password }}" not in toml_text


@pytest.mark.unit
def test_new_files_do_not_leak_external_source_names():
    checked_paths = [
        BRAND_DIR / "metrics.json",
        BRAND_DIR / "policy.json",
        BRAND_DIR / "UI.json",
        BRAND_DIR / f"{CONFIG_TYPE}.child.toml.j2",
        Path(__file__),
        WEB_ROOT / "public" / "assets" / "icons" / "mm-witek_witek.svg",
    ]
    checked_text = "\n".join(path.read_text(encoding="utf-8") for path in checked_paths)
    forbidden_terms = (
        "Data" + "dog",
        "Libre" + "NMS",
        "Zab" + "bix",
        "Check" + "mk",
        "Open" + "NMS",
        "snmp_" + "exporter",
    )
    leaked = [term for term in forbidden_terms if term in checked_text]
    assert leaked == []
