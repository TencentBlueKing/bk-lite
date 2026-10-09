"""Contract tests for the Icotera Access SNMP plugin.

Icotera A/S (enterprise PEN 29865, formerly Kjaerulff 1, EET Europarts group)
manufactures FTTH/GPON/CATV/VoIP CPE terminals in the i64xx (1K) and i68xx
(4K) families. The public ICOTERA-I6400-SERIES and ICOTERA-I6800-SERIES MIB
modules expose ictIGW1k / ictIGW4k sub-trees that cover CATV module admin
state, RF levels, optical-transceiver DDM, VoIP FXS, DHCP server leases and
port duplex. Those leaves either require per-row filtering that telegraf
inputs.snmp cannot reliably provide, or have semantics that drift across
hardware revisions, so this child is conservative: metrics.json declares no
vendor metric deltas, and the shared Access SNMP floor supplies MIB-II uptime
and IF-MIB/ifXTable 64-bit HC traffic.
"""
import json
import re
from pathlib import Path

import pytest
import yaml

from apps.core.utils.loader import LanguageLoader

SERVER_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = SERVER_ROOT.parent
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
BRAND_DIR = PLUGINS / "snmp" / "access_icotera"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = REPO_ROOT / "web"
ICON_PATH = WEB_ROOT / "public" / "assets" / "icons" / "mm-icotera_icotera.svg"

BRAND = "icotera"
COLLECT_TYPE = "snmp_icotera"
CONFIG_TYPE = "icotera"
INSTANCE_TYPE = "access"
PLUGIN_NAME = "Access Icotera SNMP"
OBJECT_NAME = "Access"
PEN_ROOT = "1.3.6.1.4.1.29865"

BASE_METRICS = {
    "snmp_uptime",
    "interface_ifHCInOctets",
    "interface_ifHCOutOctets",
    "device_total_incoming_traffic",
    "device_total_outgoing_traffic",
}
SNMP_FLOOR = {
    "snmp_uptime",
    "interface_ifHCInOctets",
    "interface_ifHCOutOctets",
}
COLLECTED_HEALTH_METRICS = {
    "transceiver_temperature_celsius",
    "transceiver_voltage_volts",
    "transceiver_tx_power_mw",
    "transceiver_rx_power_mw",
    "transceiver_tx_bias_ma",
}
HEALTH_METRIC_OIDS = {
    "transceiver_temperature_celsius": "1.3.6.1.4.1.29865.11.3.1.3.1.0",
    "transceiver_tx_power_mw": "1.3.6.1.4.1.29865.11.3.1.3.2.0",
    "transceiver_rx_power_mw": "1.3.6.1.4.1.29865.11.3.1.3.3.0",
    "transceiver_voltage_volts": "1.3.6.1.4.1.29865.11.3.1.3.4.0",
    "transceiver_tx_bias_ma": "1.3.6.1.4.1.29865.11.3.1.3.5.0",
}
UNSUPPORTED_HEALTH_METRICS = {
    "device_cpu_usage",
    "device_memory_used",
    "device_memory_free",
    "device_memory_usage",
    "device_temperature_celsius",
    "device_fan_state",
    "device_psu_state",
    "access_pon_state",
    "access_onu_state",
    "access_optical_rx_power",
    "access_optical_tx_power",
}
FORBIDDEN_SOURCE_WORDS = re.compile(
    "|".join(
        [
            "Data" + "dog",
            "Libre" + "NMS",
            "Zab" + "bix",
            "Check" + "mk",
            "Open" + "NMS",
            "OID" + "View",
            "Solar" + "Winds",
            "snmp_" + "exporter",
        ]
    ),
    re.IGNORECASE,
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
        lang: LanguageLoader("monitor", lang).translations
        for lang in ("zh-Hans", "en")
    }


@pytest.mark.unit
def test_plugin_identity_and_flat_dir(metrics, policy, ui, toml_text):
    assert BRAND_DIR.parent.name == "snmp"
    assert metrics["collector"] == "Telegraf"
    assert metrics["collect_type"] == COLLECT_TYPE
    assert metrics["plugin"] == PLUGIN_NAME
    assert metrics["name"] == OBJECT_NAME
    assert policy["object"] == OBJECT_NAME
    assert policy["plugin"] == PLUGIN_NAME
    assert ui["object_name"] == OBJECT_NAME
    assert ui["instance_type"] == INSTANCE_TYPE
    assert ui["collect_type"] == COLLECT_TYPE
    assert ui["config_type"] == [CONFIG_TYPE]
    assert f'collect_type = "{COLLECT_TYPE}"' in toml_text
    assert f'config_type = "{CONFIG_TYPE}"' in toml_text
    assert f'brand = "{BRAND}"' in toml_text
    assert f"instance_type='access', collect_type='{COLLECT_TYPE}'" in metrics["status_query"]


@pytest.mark.unit
def test_ui_is_pure_snmp_form_with_sidecar_secret_fields(ui):
    field_names = {field["name"] for field in ui["form_fields"]}
    assert "brand" not in field_names
    assert "ENV_AUTH_PASSWORD" in field_names
    assert "ENV_PRIV_PASSWORD" in field_names
    assert "auth_password" not in field_names
    assert "priv_password" not in field_names


@pytest.mark.unit
def test_metrics_json_embeds_deployed_snmp_floor(metrics):
    names = {metric["name"] for metric in metrics["metrics"]}
    assert SNMP_FLOOR <= names
    assert names - SNMP_FLOOR == COLLECTED_HEALTH_METRICS
    supplementary = set(metrics.get("supplementary_indicators", []))
    assert supplementary <= names
    assert {"snmp_uptime", "transceiver_temperature_celsius", "transceiver_voltage_volts"} <= supplementary


@pytest.mark.unit
def test_policy_is_empty_and_subset_of_metrics(metrics, policy):
    known = {metric["name"] for metric in metrics["metrics"]}
    policy_metrics = {template["metric_name"] for template in policy["templates"]}
    assert policy_metrics <= known


@pytest.mark.unit
def test_no_private_pen_collection_keeps_to_shared_floor(metrics, toml_text):
    names = {metric["name"] for metric in metrics["metrics"]}
    assert COLLECTED_HEALTH_METRICS <= names
    assert PEN_ROOT in toml_text
    for name, oid in HEALTH_METRIC_OIDS.items():
        assert oid in toml_text, f"{name} must keep explicit OID {oid}"
    leaked = sorted(names & UNSUPPORTED_HEALTH_METRICS)
    assert leaked == []
    assert "[[processors.enum]]" not in toml_text
    for marker in ("ictIGW1k", "ictIGW4k", "catvModuleAdminStatus", "ifDuplexStatus"):
        assert marker not in toml_text, (
            f"Private Icotera leaf {marker!r} requires per-row filtering and "
            "is intentionally not collected in the child"
        )


@pytest.mark.unit
def test_toml_collects_64bit_ifxtable_without_32bit_octets(toml_text):
    assert "1.3.6.1.2.1.31.1.1" in toml_text
    assert "1.3.6.1.2.1.31.1.1.1.6" in toml_text
    assert "1.3.6.1.2.1.31.1.1.1.10" in toml_text
    assert "ifDescr" in toml_text
    assert "ifHCInOctets" in toml_text
    assert "ifHCOutOctets" in toml_text
    assert 'name = "ifInOctets"' not in toml_text
    assert 'name = "ifOutOctets"' not in toml_text
    assert 'oid = "1.3.6.1.2.1.2.2.1.10"' not in toml_text
    assert 'oid = "1.3.6.1.2.1.2.2.1.16"' not in toml_text


@pytest.mark.unit
def test_toml_collects_uptime_and_uses_secret_placeholders(toml_text):
    assert "1.3.6.1.2.1.1.3.0" in toml_text
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
    en_desc = languages["en"]["monitor_object_plugin"][PLUGIN_NAME]["desc"]
    assert ": " not in en_desc


@pytest.mark.unit
def test_frontend_collecttype_and_brand_rule_are_wired():
    access_tsx = (
        WEB_ROOT / "src" / "app" / "monitor" / "hooks" / "integration"
        / "objects" / "networkDevice" / "access.tsx"
    ).read_text(encoding="utf-8")
    common_tsx = (WEB_ROOT / "src" / "app" / "monitor" / "utils" / "common.tsx").read_text(
        encoding="utf-8"
    )
    assert f"'{PLUGIN_NAME}': '{COLLECT_TYPE}'" in access_tsx
    assert "label: 'Icotera'" in common_tsx
    assert "icon: 'mm-icotera_icotera'" in common_tsx
    brand_rule = common_tsx.lower().split("label: 'icotera'")[0].split("{ match:")[-1]
    assert "access" not in brand_rule
    assert "ftth" not in brand_rule
    assert "gpon" not in brand_rule
    assert "catv" not in brand_rule
    assert "voip" not in brand_rule
    assert "cpe" not in brand_rule
    assert ICON_PATH.exists()


@pytest.mark.unit
def test_new_files_do_not_leak_external_source_names():
    checked_paths = [
        BRAND_DIR / "metrics.json",
        BRAND_DIR / "policy.json",
        BRAND_DIR / "UI.json",
        BRAND_DIR / f"{CONFIG_TYPE}.child.toml.j2",
        Path(__file__),
        WEB_ROOT / "src" / "app" / "monitor" / "hooks" / "integration" / "objects" / "networkDevice" / "access.tsx",
        WEB_ROOT / "src" / "app" / "monitor" / "utils" / "common.tsx",
        ICON_PATH,
    ]
    leaked = [
        str(path) for path in checked_paths if FORBIDDEN_SOURCE_WORDS.search(path.read_text(encoding="utf-8"))
    ]
    assert leaked == []


@pytest.mark.unit
def test_collecttype_uniqueness_in_access_object():
    """Verify there is exactly one collect_type entry for the Icotera plugin in
    the access.tsx collectTypes map (defense against 沉淀 #11 duplicate keys).
    """
    access_tsx = (
        WEB_ROOT / "src" / "app" / "monitor" / "hooks" / "integration"
        / "objects" / "networkDevice" / "access.tsx"
    ).read_text(encoding="utf-8")
    assert access_tsx.count(f"'{COLLECT_TYPE}'") == 1
    assert access_tsx.count(f"'{PLUGIN_NAME}'") == 1
