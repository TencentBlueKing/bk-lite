"""Contract tests for the V-SOL / V-SOLUTION Access SNMP plugin.

V1600D EPON OLT devices expose confirmed scalar health OIDs for CPU load,
memory load and system temperature under PEN 37950. PON, ONU, transceiver and
alarm tables are intentionally not promoted into shared device-health metrics,
and power-module state is left out until the normal-state enum is verified.
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
BRAND_DIR = PLUGINS / "snmp" / "access_vsolution"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "vsolution"
COLLECT_TYPE = "snmp_vsolution"
CONFIG_TYPE = "vsolution"
INSTANCE_TYPE = "access"
PLUGIN_NAME = "Access V-SOL SNMP"
OBJECT_NAME = "Access"
PEN_ROOT = "1.3.6.1.4.1.37950"

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
}
UNSUPPORTED_METRICS = {
    "device_fan_state",
    "device_psu_state",
    "access_pon_state",
    "access_onu_state",
    "access_optical_rx_power",
    "access_optical_tx_power",
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
def test_metrics_json_declares_only_vendor_delta_child(metrics):
    names = {metric["name"] for metric in metrics["metrics"]}
    assert names == VENDOR_METRICS
    assert names & BASE_METRICS == set()
    assert names & UNSUPPORTED_METRICS == set()
    assert set(metrics["supplementary_indicators"]) <= names


@pytest.mark.unit
def test_policy_templates_are_subset_of_metrics(metrics, policy):
    known = {metric["name"] for metric in metrics["metrics"]}
    bad = [template["metric_name"] for template in policy["templates"] if template["metric_name"] not in known]
    assert bad == []
    assert {template["metric_name"] for template in policy["templates"]} == VENDOR_METRICS


@pytest.mark.unit
def test_private_scalar_health_oids_are_collected(toml_text):
    assert PEN_ROOT in toml_text
    assert "1.3.6.1.4.1.37950.1.1.5.10.12.3.0" in toml_text
    assert "1.3.6.1.4.1.37950.1.1.5.10.12.4.0" in toml_text
    assert "1.3.6.1.4.1.37950.1.1.5.10.12.5.9.0" in toml_text


@pytest.mark.unit
def test_health_metric_queries_and_units(metrics):
    by = {metric["name"]: metric for metric in metrics["metrics"]}
    for name in ("device_cpu_usage", "device_memory_usage"):
        assert by[name]["unit"] == "percent"
        assert by[name]["query"].replace(" ", "").startswith("avg(")
        assert "by(instance_id)" in by[name]["query"].replace(" ", "")
    assert by["device_temperature_celsius"]["unit"] == "celsius"
    assert by["device_temperature_celsius"]["query"].replace(" ", "").startswith("max(")


@pytest.mark.unit
def test_unsupported_tables_not_promoted_to_health_metrics(metrics, toml_text):
    names = {metric["name"] for metric in metrics["metrics"]}
    assert names & UNSUPPORTED_METRICS == set()
    assert "powerModuleStateTable" not in toml_text
    assert "[[processors.enum]]" not in toml_text


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
    assert "1.3.6.1.2.1.31.1.1" in toml_text
    assert "ifDescr" in toml_text


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
def test_plugin_and_metrics_have_bilingual_names(languages):
    for lang, data in languages.items():
        entry = (data.get("monitor_object_plugin") or {}).get(PLUGIN_NAME) or {}
        assert entry.get("name"), f"{lang}: plugin name missing"
        assert entry.get("desc"), f"{lang}: plugin desc missing"
        metric_names = data.get("monitor_object_metric", {}).get(OBJECT_NAME, {})
        missing = [name for name in VENDOR_METRICS if name not in metric_names]
        assert missing == [], f"{lang}: Access metrics missing {missing}"


@pytest.mark.unit
def test_metric_groups_have_bilingual_names(languages):
    for lang, data in languages.items():
        groups = data.get("monitor_object_metric_group", {}).get(OBJECT_NAME, {})
        assert groups.get("Access"), f"{lang}: Access group missing"
        assert groups.get("Temperature"), f"{lang}: Temperature group missing"


@pytest.mark.unit
def test_en_desc_has_no_halfwidth_colon_space(languages):
    en = (languages["en"].get("monitor_object_plugin") or {}).get(PLUGIN_NAME) or {}
    assert ": " not in en.get("desc", "")


@pytest.mark.unit
def test_frontend_collecttype_wired_to_access_object():
    access_tsx = (
        WEB_ROOT / "src" / "app" / "monitor" / "hooks" / "integration"
        / "objects" / "networkDevice" / "access.tsx"
    )
    text = access_tsx.read_text(encoding="utf-8")
    assert f"'{PLUGIN_NAME}': '{COLLECT_TYPE}'" in text


@pytest.mark.unit
def test_brand_match_and_icon_present_in_common():
    common = WEB_ROOT / "src" / "app" / "monitor" / "utils" / "common.tsx"
    text = common.read_text(encoding="utf-8")
    assert BRAND in text
    assert "mm-vsolution_vsolution" in text
    assert (WEB_ROOT / "public" / "assets" / "icons" / "mm-vsolution_vsolution.svg").exists()


@pytest.mark.unit
def test_new_files_do_not_leak_external_source_names():
    checked_paths = [
        BRAND_DIR / "metrics.json",
        BRAND_DIR / "policy.json",
        BRAND_DIR / "UI.json",
        BRAND_DIR / f"{CONFIG_TYPE}.child.toml.j2",
        Path(__file__),
        WEB_ROOT / "public" / "assets" / "icons" / "mm-vsolution_vsolution.svg",
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
