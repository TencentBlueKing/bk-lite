"""Contract tests for the WTI console-server SNMP plugin.

WTI console and remote power devices expose console/environment objects under
PEN 2634. The plugin adds only verified device-level health leaves: unit
temperature and input-power presence states. Serial-port, plug power metering,
user and trap objects stay out of shared health metadata.
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
BRAND_DIR = PLUGINS / "snmp" / "console_server_wti"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "wti"
COLLECT_TYPE = "snmp_wti"
CONFIG_TYPE = "wti"
INSTANCE_TYPE = "console_server"
PLUGIN_NAME = "ConsoleServer WTI SNMP"
OBJECT_NAME = "ConsoleServer"
WTI_CONSOLE_ROOT = "1.3.6.1.4.1.2634.1"
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
UNSUPPORTED_METRICS = {
    "device_cpu_usage",
    "device_memory_usage",
    "device_memory_used",
    "device_memory_free",
    "device_fan_state",
    "wti_plug_current",
    "wti_plug_power",
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
def test_toml_collects_verified_wti_health_oids(toml_text):
    assert WTI_CONSOLE_ROOT in toml_text
    assert "1.3.6.1.4.1.2634.1.200.10.1.3" in toml_text
    for suffix in ("22", "23", "24", "25"):
        assert f"1.3.6.1.4.1.2634.1.200.10.1.{suffix}" in toml_text


@pytest.mark.unit
def test_metrics_json_is_brand_delta_without_base_metrics(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    assert names == EXPECTED_METRICS
    leaked = [name for name in BASE_METRICS if name in names]
    assert leaked == []
    assert metrics.get("supplementary_indicators", []) == sorted(EXPECTED_METRICS)


@pytest.mark.unit
def test_health_metrics_are_temperature_and_conservative_power_state(metrics):
    by_name = {m["name"]: m for m in metrics["metrics"]}
    assert by_name["device_temperature_celsius"]["metric_group"] == "Temperature"
    assert by_name["device_temperature_celsius"]["unit"] == "celsius"
    assert by_name["device_temperature_celsius"]["query"].replace(" ", "").startswith("max(")
    assert by_name["device_psu_state"]["metric_group"] == "Hardware Status"
    assert by_name["device_psu_state"]["data_type"] == "Enum"
    assert by_name["device_psu_state"]["unit"] == "none"
    assert by_name["device_psu_state"]["query"].replace(" ", "").startswith("max(")


@pytest.mark.unit
def test_unsupported_or_business_metrics_not_promoted(metrics, policy, toml_text):
    names = {m["name"] for m in metrics["metrics"]}
    for absent in UNSUPPORTED_METRICS:
        assert absent not in names
    assert "portTable" not in toml_text
    assert "plugCurrent" not in toml_text
    assert "plugPower" not in toml_text
    assert all(t["metric_name"] not in UNSUPPORTED_METRICS for t in policy["templates"])


@pytest.mark.unit
def test_power_state_uses_enum_default_fault(toml_text):
    assert "[[processors.enum]]" in toml_text
    assert "[[processors.starlark]]" in toml_text
    assert 'brand = ["wti"]' in toml_text
    for index in range(1, 5):
        field = f"wti_input_power_{index}_state"
        assert f'field = "{field}"' in toml_text
        assert f'dest = "{field}"' in toml_text
    assert 'metric.fields["device_psu_state"] = max(states)' in toml_text
    assert "default = 2" in toml_text
    assert '1 = 1' in toml_text


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
        assert missing == set(), f"{lang}: ConsoleServer metrics missing {missing}"
        groups = data.get("monitor_object_metric_group", {}).get(OBJECT_NAME, {})
        assert groups.get("Temperature")
        assert groups.get("Hardware Status")


@pytest.mark.unit
def test_en_desc_has_no_halfwidth_colon_space(languages):
    en = (languages["en"].get("monitor_object_plugin") or {}).get(PLUGIN_NAME) or {}
    assert ": " not in en.get("desc", "")


@pytest.mark.unit
def test_frontend_collecttype_wired_to_console_server_object():
    ns_tsx = WEB_ROOT / "src" / "app" / "monitor" / "hooks" / "integration" / "objects" / "networkDevice" / "consoleServer.tsx"
    assert f"'{PLUGIN_NAME}': '{COLLECT_TYPE}'" in ns_tsx.read_text(encoding="utf-8")


@pytest.mark.unit
def test_brand_label_present_in_common_without_generic_terms():
    common = WEB_ROOT / "src" / "app" / "monitor" / "utils" / "common.tsx"
    text = common.read_text(encoding="utf-8")
    assert "WTI" in text
    assert "mm-wti_wti" in text
    assert "western\\s*telematic" in text.lower()
    wti_line = next(line for line in text.splitlines() if "mm-wti_wti" in line)
    assert "console" not in wti_line.lower()
    assert "power" not in wti_line.lower()


@pytest.mark.unit
def test_brand_svg_exists():
    assert (WEB_ROOT / "public" / "assets" / "icons" / "mm-wti_wti.svg").exists()


@pytest.mark.unit
def test_brand_files_have_no_external_source_residue():
    forbidden = [
        "Da" + "tadog",
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
        WEB_ROOT / "public" / "assets" / "icons" / "mm-wti_wti.svg"
    ]
    offenders = {
        path.name: [word for word in forbidden if word in path.read_text(encoding="utf-8")]
        for path in paths
        if path.is_file()
    }
    offenders = {name: words for name, words in offenders.items() if words}
    assert offenders == {}
