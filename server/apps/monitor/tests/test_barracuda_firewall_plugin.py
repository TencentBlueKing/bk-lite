"""Contract tests for the Barracuda firewall SNMP plugin.

Barracuda exposes verified bspyware system leaves under PEN 20632 for CPU and
system temperature plus firmware/log storage. Fan RPM and dead-fan traps are not
state leaves, so this plugin does not promote them to device_fan_state.
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
BRAND_DIR = PLUGINS / "snmp" / "firewall_barracuda"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "barracuda"
COLLECT_TYPE = "snmp_barracuda"
CONFIG_TYPE = "barracuda"
INSTANCE_TYPE = "firewall"
PLUGIN_NAME = "Firewall Barracuda SNMP"
OBJECT_NAME = "Firewall"
BSPYWARE_SYSTEM_ROOT = "1.3.6.1.4.1.20632.3.1.10"
EXPECTED_METRICS = {
    "device_temperature_celsius",
    "device_disk_usage",
}
BASE_METRICS = {
    "snmp_uptime",
    "interface_ifHCInOctets",
    "interface_ifHCOutOctets",
    "device_total_incoming_traffic",
    "device_total_outgoing_traffic",
}
UNSUPPORTED_METRICS = {
    "device_cpu_usage",
    "device_memory_usage",
    "device_memory_used",
    "device_memory_free",
    "device_fan_state",
    "device_psu_state",
    "barracuda_cpu_fan_speed",
    "barracuda_system_fan_speed",
}
FORBIDDEN_SOURCE_WORDS = (
    "Data" + "dog",
    "Libre" + "NMS",
    "Za" + "bbix",
    "Check" + "mk",
    "Open" + "NMS",
    "Obser" + "vium",
    "snmp_" + "exporter",
    "cent" + "reon",
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
def test_toml_collects_verified_barracuda_health_oids(toml_text):
    assert BSPYWARE_SYSTEM_ROOT in toml_text
    for suffix in ("3", "4", "5", "6"):
        assert f"{BSPYWARE_SYSTEM_ROOT}.{suffix}.0" in toml_text


@pytest.mark.unit
def test_metrics_json_is_brand_delta_without_base_metrics(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    assert names == EXPECTED_METRICS
    assert not (names & BASE_METRICS)
    assert metrics.get("supplementary_indicators", []) == sorted(EXPECTED_METRICS)


@pytest.mark.unit
def test_health_metrics_are_temperature_and_disk_usage(metrics):
    by_name = {m["name"]: m for m in metrics["metrics"]}
    assert by_name["device_temperature_celsius"]["metric_group"] == "Temperature"
    assert by_name["device_temperature_celsius"]["unit"] == "celsius"
    assert by_name["device_temperature_celsius"]["query"].replace(" ", "").startswith("max(")
    assert by_name["device_disk_usage"]["metric_group"] == "Hardware Status"
    assert by_name["device_disk_usage"]["unit"] == "percent"
    assert by_name["device_disk_usage"]["query"].replace(" ", "").startswith("max(")


@pytest.mark.unit
def test_unsupported_metrics_not_promoted(metrics, policy, toml_text):
    names = {m["name"] for m in metrics["metrics"]}
    for absent in UNSUPPORTED_METRICS:
        assert absent not in names
    assert "cpuFanSpeed" not in toml_text
    assert "systemFanSpeed" not in toml_text
    assert all(t["metric_name"] not in UNSUPPORTED_METRICS for t in policy["templates"])


@pytest.mark.unit
def test_starlark_aggregates_temperature_and_storage_worst_values(toml_text):
    assert "[[processors.starlark]]" in toml_text
    assert 'brand = ["barracuda"]' in toml_text
    assert 'metric.fields["device_temperature_celsius"] = max(' in toml_text
    assert 'metric.fields["device_disk_usage"] = max(' in toml_text


@pytest.mark.unit
def test_toml_collects_uptime_and_64bit_ifhc_counters(toml_text):
    assert "1.3.6.1.2.1.1.3.0" in toml_text
    assert "1.3.6.1.2.1.31.1.1.1.6" in toml_text
    assert "1.3.6.1.2.1.31.1.1.1.10" in toml_text
    assert "1.3.6.1.2.1.2.2.1.10" not in toml_text
    assert "1.3.6.1.2.1.2.2.1.16" not in toml_text


@pytest.mark.unit
def test_policy_templates_reference_existing_metrics(metrics, policy):
    known = {m["name"] for m in metrics["metrics"]}
    bad = [t["metric_name"] for t in policy["templates"] if t["metric_name"] not in known]
    assert bad == []


@pytest.mark.unit
def test_plugin_metrics_and_groups_have_bilingual_names(languages):
    for lang, data in languages.items():
        entry = (data.get("monitor_object_plugin") or {}).get(PLUGIN_NAME) or {}
        assert entry.get("name"), f"{lang}: plugin name missing"
        assert entry.get("desc"), f"{lang}: plugin desc missing"
        metric_names = data.get("monitor_object_metric", {}).get(OBJECT_NAME, {})
        missing = EXPECTED_METRICS - set(metric_names)
        assert missing == set(), f"{lang}: Firewall metrics missing {missing}"
        groups = data.get("monitor_object_metric_group", {}).get(OBJECT_NAME, {})
        assert groups.get("Temperature")
        assert groups.get("Hardware Status")


@pytest.mark.unit
def test_en_desc_has_no_halfwidth_colon_space(languages):
    en = (languages["en"].get("monitor_object_plugin") or {}).get(PLUGIN_NAME) or {}
    assert ": " not in en.get("desc", "")


@pytest.mark.unit
def test_frontend_collecttype_and_brand_mapping_exist():
    firewall_tsx = (
        WEB_ROOT / "src" / "app" / "monitor" / "hooks" / "integration"
        / "objects" / "networkDevice" / "firewall.tsx"
    )
    common_tsx = WEB_ROOT / "src" / "app" / "monitor" / "utils" / "common.tsx"
    assert f"'{PLUGIN_NAME}': '{COLLECT_TYPE}'" in firewall_tsx.read_text(encoding="utf-8")
    common_text = common_tsx.read_text(encoding="utf-8")
    assert "barracuda" in common_text
    assert "mm-barracuda_barracuda" in common_text


@pytest.mark.unit
def test_brand_icon_exists():
    assert (WEB_ROOT / "public" / "assets" / "icons" / "mm-barracuda_barracuda.svg").exists()


@pytest.mark.unit
def test_no_external_source_keywords_in_brand_files():
    checked = list(BRAND_DIR.glob("*")) + [
        WEB_ROOT / "public" / "assets" / "icons" / "mm-barracuda_barracuda.svg",
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in checked if path.is_file())
    leaked = [word for word in FORBIDDEN_SOURCE_WORDS if word.lower() in text.lower()]
    assert leaked == []
