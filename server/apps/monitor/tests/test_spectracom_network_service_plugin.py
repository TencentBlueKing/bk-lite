"""Contract tests for the Spectracom NetworkService SNMP plugin.

Spectracom time servers expose confirmed xSync and NTP status scalars under PEN
18837. The plugin collects only status values with clear enum semantics and the
shared SNMP floor; temperature and hot-swap leaves are intentionally skipped
until their complete numeric leaves are verified.
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
BRAND_DIR = PLUGINS / "snmp" / "network_service_spectracom"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "spectracom"
COLLECT_TYPE = "snmp_spectracom"
CONFIG_TYPE = "spectracom"
INSTANCE_TYPE = "network_service"
PLUGIN_NAME = "NetworkService Spectracom SNMP"
OBJECT_NAME = "NetworkService"
PEN_ROOT = "1.3.6.1.4.1.18837"

BASE_METRICS = (
    "snmp_uptime",
    "interface_ifHCInOctets",
    "interface_ifHCOutOctets",
    "device_total_incoming_traffic",
    "device_total_outgoing_traffic",
)
EXPECTED_METRICS = {
    "network_service_spectracom_sync_state",
    "network_service_spectracom_dc_power_state",
    "network_service_spectracom_minor_alarm_state",
    "network_service_spectracom_major_alarm_state",
    "network_service_spectracom_ntp_state",
    "network_service_spectracom_ntp_stratum",
}
UNSUPPORTED_HEALTH_METRICS = (
    "device_cpu_usage",
    "device_memory_usage",
    "device_memory_used",
    "device_memory_free",
    "device_temperature_celsius",
    "device_fan_state",
    "device_psu_state",
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
def test_metrics_json_declares_only_vendor_delta_metrics(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    assert names == EXPECTED_METRICS
    leaked = [name for name in BASE_METRICS if name in names]
    assert leaked == []


@pytest.mark.unit
def test_unsupported_shared_health_metrics_are_not_guessed(metrics, toml_text):
    names = {m["name"] for m in metrics["metrics"]}
    for absent in UNSUPPORTED_HEALTH_METRICS:
        assert absent not in names
        assert absent not in toml_text
    assert "temperature" not in toml_text.lower()
    assert "hotswap" not in toml_text.lower()


@pytest.mark.unit
def test_policy_templates_reference_existing_metrics(metrics, policy):
    known = {m["name"] for m in metrics["metrics"]}
    bad = [t["metric_name"] for t in policy["templates"] if t["metric_name"] not in known]
    assert bad == []


@pytest.mark.unit
def test_toml_collects_confirmed_spectracom_oids(toml_text):
    assert PEN_ROOT in toml_text
    for oid in (
        "1.3.6.1.4.1.18837.3.2.2.1.2",
        "1.3.6.1.4.1.18837.3.2.2.1.5",
        "1.3.6.1.4.1.18837.3.2.2.1.13",
        "1.3.6.1.4.1.18837.3.2.2.1.14",
        "1.3.6.1.4.1.18837.3.3.2.1",
        "1.3.6.1.4.1.18837.3.3.2.2",
    ):
        assert oid in toml_text


@pytest.mark.unit
def test_toml_collects_uptime_and_64bit_ifhc_counters(toml_text):
    assert "1.3.6.1.2.1.1.3.0" in toml_text
    assert "1.3.6.1.2.1.31.1.1.1.6" in toml_text
    assert "1.3.6.1.2.1.31.1.1.1.10" in toml_text
    assert "1.3.6.1.2.1.2.2.1.10" not in toml_text
    assert "1.3.6.1.2.1.2.2.1.16" not in toml_text


@pytest.mark.unit
def test_status_enums_are_conservatively_normalized(toml_text):
    assert "processors.enum" in toml_text
    assert 'brand = ["spectracom"]' in toml_text
    assert 'field = "network_service_spectracom_sync_state"' in toml_text
    assert 'field = "network_service_spectracom_dc_power_state"' in toml_text
    assert 'field = "network_service_spectracom_major_alarm_state"' in toml_text
    assert 'field = "network_service_spectracom_ntp_state"' in toml_text
    assert "default = 2" in toml_text
    assert "4 = 1" in toml_text


@pytest.mark.unit
def test_plugin_has_bilingual_name_desc_and_metric_translations(metrics, languages):
    metric_names = {m["name"] for m in metrics["metrics"]}
    for lang, data in languages.items():
        entry = (data.get("monitor_object_plugin") or {}).get(PLUGIN_NAME) or {}
        assert entry.get("name"), f"{lang}: plugin name missing"
        assert entry.get("desc"), f"{lang}: plugin desc missing"
        metric_i18n = (data.get("monitor_object_metric") or {}).get(OBJECT_NAME) or {}
        missing = [name for name in metric_names if name not in metric_i18n]
        assert missing == [], f"{lang}: metric translations missing {missing}"


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
    assert "Spectracom" in text
    assert "mm-spectracom_spectracom" in text
    spectracom_line = next(line for line in text.splitlines() if "mm-spectracom_spectracom" in line)
    assert "ntp" not in spectracom_line.lower()
    assert "ptp" not in spectracom_line.lower()
    assert "time" not in spectracom_line.lower()
    assert "server" not in spectracom_line.lower()


@pytest.mark.unit
def test_brand_svg_exists():
    assert (WEB_ROOT / "public" / "assets" / "icons" / "mm-spectracom_spectracom.svg").exists()


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
        WEB_ROOT / "public" / "assets" / "icons" / "mm-spectracom_spectracom.svg"
    ]
    offenders = {
        path.name: [word for word in forbidden if word in path.read_text(encoding="utf-8")]
        for path in paths
        if path.is_file()
    }
    offenders = {name: words for name, words in offenders.items() if words}
    assert offenders == {}
