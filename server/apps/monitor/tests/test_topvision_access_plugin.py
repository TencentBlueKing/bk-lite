"""Contract tests for the Topvision (Sumavision) Access SNMP plugin.

The state source confirms the IANA enterprise root PEN 32285 for Sumavision
Technologies Co., Ltd, the public OS-class registration for Topvision with a
real sysObjectID, and the Sumavision official homepage. The publicly known
Topvision handler only collects an HM800MIB RAID table (Hitachi RAID MIB
borrowed out of context) plus a few scalar inventory OIDs, and no stable
shared private CPU, memory, temperature, fan or power-supply health leaf OID
is confirmed in this workspace. This child is therefore conservative:
metrics.json declares no vendor metric deltas, while the shared Access SNMP
floor supplies uptime, IF-MIB/ifXTable traffic and aggregate device traffic.
"""
import json
import re
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = SERVER_ROOT.parent
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
BRAND_DIR = PLUGINS / "snmp" / "access_topvision"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = REPO_ROOT / "web"
ICON_PATH = WEB_ROOT / "public" / "assets" / "icons" / "mm-topvision_topvision.svg"

BRAND = "topvision"
COLLECT_TYPE = "snmp_topvision"
CONFIG_TYPE = "topvision"
INSTANCE_TYPE = "access"
PLUGIN_NAME = "Access Topvision SNMP"
OBJECT_NAME = "Access"
PEN_ROOT = "1.3.6.1.4.1.32285"
HM800_MARKERS = ("HM800", "raidExMibRaidListTable", "raidExMib")

BASE_METRICS = {
    "snmp_uptime",
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
        lang: yaml.safe_load((LANGUAGE_DIR / f"{lang}.yaml").read_text(encoding="utf-8"))
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
def test_metrics_json_declares_zero_vendor_delta_child(metrics):
    names = {metric["name"] for metric in metrics["metrics"]}
    assert names == set()
    assert names & BASE_METRICS == set()
    assert names & HEALTH_METRICS == set()
    assert metrics["supplementary_indicators"] == []


@pytest.mark.unit
def test_policy_is_empty_and_subset_of_metrics(metrics, policy):
    known = {metric["name"] for metric in metrics["metrics"]}
    policy_metrics = {template["metric_name"] for template in policy["templates"]}
    assert policy_metrics <= known
    assert policy["templates"] == []


@pytest.mark.unit
def test_no_private_health_or_borrowed_hm800_raid_collection(toml_text):
    assert PEN_ROOT not in toml_text
    for marker in HM800_MARKERS:
        assert marker not in toml_text, (
            f"HM800 RAID borrow is out of CMTS scope and must not be collected: {marker}"
        )
    assert "[[processors.enum]]" not in toml_text


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
    assert "label: 'Topvision'" in common_tsx
    assert "icon: 'mm-topvision_topvision'" in common_tsx
    brand_rule = common_tsx.lower().split("label: 'topvision'")[0].split("{ match:")[-1]
    assert "access" not in brand_rule
    assert "cmts" not in brand_rule
    assert "cable" not in brand_rule
    assert "docsis" not in brand_rule
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
