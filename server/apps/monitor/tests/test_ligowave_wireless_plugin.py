"""Contract tests for the LigoWave wireless SNMP plugin.

LigoWave wireless AP / backhaul devices use enterprise PEN 32750. The confirmed
MIB facts cover wireless interface, remote-node, signal/noise/SNR, Tx power and
byte-counter telemetry, but no stable row-filter-free CPU, memory, temperature,
fan or power-supply device-health OID is confirmed for this pass. The plugin is
therefore a zero-delta Wireless child: metrics.json declares no vendor-specific
metrics, while the Telegraf child keeps sysUpTime and 64-bit IF-MIB HC
collection for the shared Wireless SNMP floor.
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
BRAND_DIR = PLUGINS / "snmp" / "wireless_ligowave"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "ligowave"
COLLECT_TYPE = "snmp_ligowave"
CONFIG_TYPE = "ligowave"
INSTANCE_TYPE = "wireless"
PLUGIN_NAME = "Wireless LigoWave SNMP"
OBJECT_NAME = "Wireless"
PEN_ROOT = "1.3.6.1.4.1.32750"

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
HEALTH_METRICS = {
    "device_cpu_usage",
    "device_memory_used",
    "device_memory_free",
    "device_memory_usage",
    "device_temperature_celsius",
    "wireless_client_count",
    "wireless_channel_utilization",
    "wireless_signal_strength",
    "device_fan_state",
    "device_psu_state",
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
def test_metrics_json_declares_zero_vendor_delta_child(metrics):
    names = {metric["name"] for metric in metrics["metrics"]}
    assert names == set()
    assert names & BASE_METRICS == set()
    assert names & HEALTH_METRICS == set()
    assert metrics["supplementary_indicators"] == []


@pytest.mark.unit
def test_policy_is_empty_and_subset_of_metrics(metrics, policy):
    known = {metric["name"] for metric in metrics["metrics"]}
    bad = [template["metric_name"] for template in policy["templates"] if template["metric_name"] not in known]
    assert bad == []
    assert policy["templates"] == []


@pytest.mark.unit
def test_no_private_health_metrics_or_pen_oid_are_collected(toml_text):
    assert PEN_ROOT not in toml_text
    for name in HEALTH_METRICS:
        assert name.replace("device_", "") not in toml_text
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
    assert "1.3.6.1.2.1.2.2" in toml_text
    assert "ifDescr" in toml_text


@pytest.mark.unit
def test_passwords_use_sidecar_env_placeholders_not_plaintext(ui, toml_text):
    fields = {field["name"]: field for field in ui["form_fields"]}
    assert "ENV_AUTH_PASSWORD" in fields
    assert "ENV_PRIV_PASSWORD" in fields
    assert "auth_password" not in fields
    assert "priv_password" not in fields
    assert fields["ENV_AUTH_PASSWORD"].get("encrypted") is True
    assert fields["ENV_PRIV_PASSWORD"].get("encrypted") is True
    assert fields["ENV_AUTH_PASSWORD"]["transform_on_edit"]["origin_path"] == (
        "child.env_config.AUTH_PASSWORD__{{config_id}}"
    )
    assert fields["ENV_PRIV_PASSWORD"]["transform_on_edit"]["origin_path"] == (
        "child.env_config.PRIV_PASSWORD__{{config_id}}"
    )
    assert 'auth_password = "${AUTH_PASSWORD__{{ config_id }}}"' in toml_text
    assert 'priv_password = "${PRIV_PASSWORD__{{ config_id }}}"' in toml_text
    assert "{{ auth_password }}" not in toml_text
    assert "{{ priv_password }}" not in toml_text


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
def test_frontend_collecttype_wired_to_wireless_object():
    wireless_tsx = (
        WEB_ROOT / "src" / "app" / "monitor" / "hooks" / "integration"
        / "objects" / "networkDevice" / "wireless.tsx"
    )
    text = wireless_tsx.read_text(encoding="utf-8")
    assert f"'{PLUGIN_NAME}': '{COLLECT_TYPE}'" in text


@pytest.mark.unit
def test_brand_match_and_icon_present_in_common():
    common = WEB_ROOT / "src" / "app" / "monitor" / "utils" / "common.tsx"
    text = common.read_text(encoding="utf-8")
    assert BRAND in text
    assert "mm-ligowave_ligowave" in text
    assert (WEB_ROOT / "public" / "assets" / "icons" / "mm-ligowave_ligowave.svg").exists()


@pytest.mark.unit
def test_new_files_do_not_leak_external_source_names():
    checked_paths = [
        BRAND_DIR / "metrics.json",
        BRAND_DIR / "policy.json",
        BRAND_DIR / "UI.json",
        BRAND_DIR / f"{CONFIG_TYPE}.child.toml.j2",
        Path(__file__),
        WEB_ROOT / "public" / "assets" / "icons" / "mm-ligowave_ligowave.svg",
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
