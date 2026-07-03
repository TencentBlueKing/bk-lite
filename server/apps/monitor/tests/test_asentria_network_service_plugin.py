"""Contract tests for the Asentria NetworkService SNMP plugin.

Asentria SiteBoss devices expose PEN 3052 and configurable EventSensor tables.
Those tables are site-specific and require row-level interpretation before
temperature, humidity, contact, or power-output points can be promoted safely.
This plugin therefore keeps a conservative baseline child for the current tick.
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
BRAND_DIR = PLUGINS / "snmp" / "network_service_asentria"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "asentria"
COLLECT_TYPE = "snmp_asentria"
CONFIG_TYPE = "asentria"
INSTANCE_TYPE = "network_service"
PLUGIN_NAME = "NetworkService Asentria SiteBoss SNMP"
OBJECT_NAME = "NetworkService"
PEN_ROOT = "1.3.6.1.4.1.3052"

BASE_METRICS = (
    "snmp_uptime",
    "interface_ifHCInOctets",
    "interface_ifHCOutOctets",
    "device_total_incoming_traffic",
    "device_total_outgoing_traffic",
)
UNSUPPORTED_HEALTH_METRICS = (
    "device_cpu_usage",
    "device_memory_usage",
    "device_memory_used",
    "device_memory_free",
    "device_temperature_celsius",
    "device_fan_state",
    "device_psu_state",
)
UNSUPPORTED_EVENT_SENSOR_METRICS = (
    "asentria_temperature",
    "asentria_humidity",
    "asentria_contact_state",
    "asentria_power_output_state",
    "asentria_alarm_state",
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
def test_asentria_event_sensor_health_oids_are_not_guessed(metrics, policy, toml_text):
    names = {m["name"] for m in metrics["metrics"]}
    for absent in UNSUPPORTED_HEALTH_METRICS + UNSUPPORTED_EVENT_SENSOR_METRICS:
        assert absent not in names
        assert absent not in toml_text
    assert PEN_ROOT not in toml_text
    assert "esPoint" not in toml_text
    assert policy["templates"] == []


@pytest.mark.unit
def test_metrics_json_is_zero_delta_child(metrics):
    assert metrics["metrics"] == []
    assert metrics.get("supplementary_indicators", []) == []
    names = {m["name"] for m in metrics["metrics"]}
    leaked = [name for name in BASE_METRICS if name in names]
    assert leaked == []


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
def test_no_enum_block_without_status_health_metrics(toml_text):
    assert "processors.enum" not in toml_text


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
def test_frontend_collecttype_wired_to_network_service_object():
    ns_tsx = (
        WEB_ROOT / "src" / "app" / "monitor" / "hooks" / "integration"
        / "objects" / "networkDevice" / "networkService.tsx"
    )
    text = ns_tsx.read_text(encoding="utf-8")
    assert f"'{PLUGIN_NAME}': '{COLLECT_TYPE}'" in text


@pytest.mark.unit
def test_brand_label_present_in_common_without_generic_terms():
    common = WEB_ROOT / "src" / "app" / "monitor" / "utils" / "common.tsx"
    text = common.read_text(encoding="utf-8")
    assert "Asentria" in text
    assert "mm-asentria_asentria" in text
    asentria_line = next(line for line in text.splitlines() if "mm-asentria_asentria" in line)
    assert "temperature" not in asentria_line.lower()
    assert "sensor" not in asentria_line.lower()
    assert "power" not in asentria_line.lower()
    assert "network" not in asentria_line.lower()


@pytest.mark.unit
def test_brand_svg_exists():
    assert (WEB_ROOT / "public" / "assets" / "icons" / "mm-asentria_asentria.svg").exists()


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
    ]
    paths = list(BRAND_DIR.glob("*")) + [
        WEB_ROOT / "public" / "assets" / "icons" / "mm-asentria_asentria.svg"
    ]
    offenders = {
        path.name: [word for word in forbidden if word in path.read_text(encoding="utf-8")]
        for path in paths
        if path.is_file()
    }
    offenders = {name: words for name, words in offenders.items() if words}
    assert offenders == {}
