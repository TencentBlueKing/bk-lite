"""Contract tests for the IP Infusion Switch SNMP plugin.

IP Infusion Inc (OcNOS) is a network-OS vendor that runs on white-box
hardware platforms such as Edgecore/Accton, UfiSpace, Delta, and Celestica.
The public enterprise root is PEN 36673 (IANA `36673 = IP Infusion Inc`,
contact `vishwas@ipinfusion.com`).

The public IPI-CMM-CHASSIS-MIB exposes chassis-level management objects
covering stack-unit inventory, fan, power-supply temperature, transceiver
temperature, and an aggregated `SystemStatusCode` bitset. The
IPI-CMM-IPMI-MIB adds an IPMI sensor table.

In this baseline the plugin declares a single chassis-level PSU 1
temperature scalar (`cmmSysPSTemperature1`) as its vendor incremental child.
Per-row tables (`cmmFanTable`, `cmmIpmiDeviceSensorTable`,
`cmmTransTemperature`) and the additional chassis scalars
`cmmSysPSTemperature2` and `cmmSysPSTemperature3` are intentionally not
collected: telegraf inputs.snmp cannot reliably aggregate per-row indices
or arithmetic-merge sibling chassis scalars into a single bk-lite metric,
so they are kept as N/A to honor the no-fabricated-health-metrics rule.
"""
import json
import re
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = SERVER_ROOT.parent
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
BRAND_DIR = PLUGINS / "snmp" / "switch_ipinfusion"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = REPO_ROOT / "web"
ICON_PATH = WEB_ROOT / "public" / "assets" / "icons" / "mm-ipinfusion_ipinfusion.svg"

BRAND = "ipinfusion"
COLLECT_TYPE = "snmp_ipinfusion"
CONFIG_TYPE = "ipinfusion"
INSTANCE_TYPE = "switch"
PLUGIN_NAME = "Switch IP Infusion SNMP"
OBJECT_NAME = "Switch"
PEN_ROOT = "1.3.6.1.4.1.36673"

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
    "device_fan_rpm",
    "device_psu_state",
    "device_transceiver_temperature_celsius",
    "device_ipmi_temperature_celsius",
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
    assert f"instance_type='switch', collect_type='{COLLECT_TYPE}'" in metrics["status_query"]


@pytest.mark.unit
def test_ui_is_pure_snmp_form_with_sidecar_secret_fields(ui):
    field_names = {field["name"] for field in ui["form_fields"]}
    assert "brand" not in field_names
    assert "ENV_AUTH_PASSWORD" in field_names
    assert "ENV_PRIV_PASSWORD" in field_names
    assert "auth_password" not in field_names
    assert "priv_password" not in field_names


@pytest.mark.unit
def test_metrics_json_declares_only_psu_temperature_vendor_delta(metrics):
    names = {metric["name"] for metric in metrics["metrics"]}
    assert names == {"device_psu_temperature_celsius"}
    # Anti-baseline-metric assertions
    assert names & BASE_METRICS == set()
    # Anti-fabricated-health assertions: per-row / heterogeneous sensor
    # leaves must NOT be promoted as scalar bk-lite metrics.
    forbidden_vendor_metric_names = (
        HEALTH_METRICS - {"device_temperature_celsius"}
    )
    assert names & forbidden_vendor_metric_names == set()
    assert metrics["supplementary_indicators"] == ["device_psu_temperature_celsius"]


@pytest.mark.unit
def test_policy_subset_of_metrics(metrics, policy):
    known = {metric["name"] for metric in metrics["metrics"]}
    policy_metrics = {template["metric_name"] for template in policy["templates"]}
    assert policy_metrics <= known
    assert len(policy["templates"]) >= 1


@pytest.mark.unit
def test_no_per_row_or_arbitrary_sibling_scalar_collected_in_toml(toml_text):
    # IPI-CMM-CHASSIS-MIB exposes per-row tables that telegraf inputs.snmp
    # cannot aggregate into a single bk-lite scalar metric, and sibling
    # chassis scalars (PSU 2/3) that would need arithmetic merging.
    # The baseline intentionally does NOT collect any of them. Scan only
    # TOML body lines (strip comments) to avoid false positives from
    # rationale comments naming the dropped leaves.
    body_lines = "\n".join(
        line for line in toml_text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    )
    for forbidden in (
        "cmmFanTable",
        "cmmFanRpm",
        "cmmFanStatus",
        "cmmIpmiDeviceSensorTable",
        "cmmIpmiDeviceSensorValue",
        "cmmTransTemperature",
        "1.3.6.1.4.1.36673.100.2.2.0",
        "1.3.6.1.4.1.36673.100.2.3.0",
        "SystemStatusCode",
    ):
        assert forbidden not in body_lines, (
            f"Baseline TOML should not collect per-row / sibling scalar leaf {forbidden!r}"
        )
    assert "[[processors.enum]]" not in body_lines
    # Only the single chassis-level PSU 1 scalar is collected
    assert "1.3.6.1.4.1.36673.100.2.1.0" in body_lines
    assert "device_psu_temperature_celsius" in body_lines


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
    switch_tsx = (
        WEB_ROOT / "src" / "app" / "monitor" / "hooks" / "integration"
        / "objects" / "networkDevice" / "switch.tsx"
    ).read_text(encoding="utf-8")
    common_tsx = (WEB_ROOT / "src" / "app" / "monitor" / "utils" / "common.tsx").read_text(
        encoding="utf-8"
    )
    assert f"'{PLUGIN_NAME}': '{COLLECT_TYPE}'" in switch_tsx
    assert "label: 'IP Infusion'" in common_tsx
    assert "icon: 'mm-ipinfusion_ipinfusion'" in common_tsx
    # Brand rule must not match generic technology / object-class terms.
    # Use word-boundary regex so substrings like "nos" inside "ocnos" don't
    # falsely trip the assertion (the rule uses `\bocnos\b` which only
    # matches the literal product name, not the generic term "nos").
    brand_rule = (
        common_tsx.lower().split("label: 'ip infusion'")[0].split("{ match:")[-1]
    )
    for forbidden in ("switch", "router", "firewall", r"\bnos\b", "white-?box", "wbos"):
        assert not re.search(forbidden, brand_rule), (
            f"Brand rule should not match generic term {forbidden!r}"
        )
    assert ICON_PATH.exists()


@pytest.mark.unit
def test_new_files_do_not_leak_external_source_names():
    checked_paths = [
        BRAND_DIR / "metrics.json",
        BRAND_DIR / "policy.json",
        BRAND_DIR / "UI.json",
        BRAND_DIR / f"{CONFIG_TYPE}.child.toml.j2",
        Path(__file__),
        WEB_ROOT / "src" / "app" / "monitor" / "hooks" / "integration" / "objects" / "networkDevice" / "switch.tsx",
        WEB_ROOT / "src" / "app" / "monitor" / "utils" / "common.tsx",
        ICON_PATH,
    ]
    leaked = [
        str(path) for path in checked_paths if FORBIDDEN_SOURCE_WORDS.search(path.read_text(encoding="utf-8"))
    ]
    assert leaked == []


@pytest.mark.unit
def test_collecttype_uniqueness_in_switch_object():
    """Verify there is exactly one collect_type entry for the IP Infusion
    plugin in the switch.tsx collectTypes map (defense against 沉淀 #11
    duplicate keys).
    """
    switch_tsx = (
        WEB_ROOT / "src" / "app" / "monitor" / "hooks" / "integration"
        / "objects" / "networkDevice" / "switch.tsx"
    ).read_text(encoding="utf-8")
    assert switch_tsx.count(f"'{COLLECT_TYPE}'") == 1
    assert switch_tsx.count(f"'{PLUGIN_NAME}'") == 1