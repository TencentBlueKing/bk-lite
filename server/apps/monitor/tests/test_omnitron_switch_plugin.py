"""Contract tests for the Omnitron Systems Technology Switch SNMP plugin.

Omnitron Systems Technology, Inc. (IANA enterprise number 7342, contact
Steve Mood, smood@omnitron-systems.com, 38 Tesla, Irvine CA 92618-4670)
manufactures the iConverter family of industrial Ethernet media converters
and fiber transceiver modules, managed by NetOutlook via OMNITRON-MIB.

The public OMNITRON-MIB / OMNITRON-POE-MIB / OMNITRON-TC-MIB expose
icAgent(1) / prodAgent(2) / omnitronProducts(5) + managementModule(1) +
omnitronMIB(3) inventory and per-port PoE power budget leaves, but every
published health-related leaf is per-management-module or per-port, which
telegraf inputs.snmp cannot aggregate into a single bk-lite device_* metric,
so this baseline intentionally does not promote any private leaf into a
vendor incremental child (zero vendor child). The shared Switch SNMP floor
supplies MIB-II uptime and IF-MIB 64-bit HC interface traffic only.
"""
import json
import re
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = SERVER_ROOT.parent
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
BRAND_DIR = PLUGINS / "snmp" / "switch_omnitron"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = REPO_ROOT / "web"
ICON_PATH = WEB_ROOT / "public" / "assets" / "icons" / "mm-omnitron_omnitron.svg"

BRAND = "omnitron"
COLLECT_TYPE = "snmp_omnitron"
CONFIG_TYPE = "omnitron"
INSTANCE_TYPE = "switch"
PLUGIN_NAME = "Switch Omnitron SNMP"
OBJECT_NAME = "Switch"
PEN_ROOT = "1.3.6.1.4.1.7342"

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
    "device_psu_temperature_celsius",
    "device_transceiver_temperature_celsius",
    "device_ipmi_temperature_celsius",
    "device_poe_power_budget_watts",
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
def test_metrics_json_declares_only_vendor_delta_with_zero_child_baseline(metrics):
    """Omnitron has no stable, row-free chassis-level scalar health
    object that bk-lite can promote to a single device_* metric, so
    this plugin follows the conservative zero-vendor-child baseline.
    """
    names = {metric["name"] for metric in metrics["metrics"]}
    assert names == set()
    # Anti-baseline-metric assertions
    assert names & BASE_METRICS == set()
    # Anti-fabricated-health assertions: per-port / per-management-module
    # leaves must NOT be promoted as scalar bk-lite metrics.
    assert names & HEALTH_METRICS == set()
    assert metrics["supplementary_indicators"] == []


@pytest.mark.unit
def test_policy_subset_of_metrics(metrics, policy):
    known = {metric["name"] for metric in metrics["metrics"]}
    policy_metrics = {template["metric_name"] for template in policy["templates"]}
    assert policy_metrics <= known
    assert policy["templates"] == []


@pytest.mark.unit
def test_toml_does_not_collect_per_port_or_per_module_pen7342_leaves(toml_text):
    """OMNITRON-MIB / OMNITRON-POE-MIB / OMNITRON-TC-MIB expose only
    per-management-module / per-port rows. telegraf inputs.snmp cannot
    aggregate those into a single bk-lite scalar, so the baseline
    intentionally does NOT collect any of them. Scan only TOML body
    lines (strip comments) to avoid false positives from rationale
    comments naming the dropped leaves.
    """
    body_lines = "\n".join(
        line for line in toml_text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    )
    for forbidden in (
        "icAgent",
        "prodAgent",
        "omnitronProducts",
        "managementModule",
        "omnitronMIB",
        PEN_ROOT,
        "1.3.6.1.4.1.7342",
    ):
        assert forbidden not in body_lines, (
            f"Baseline TOML should not collect Omnitron private leaf {forbidden!r}"
        )
    assert "[[processors.enum]]" not in body_lines
    # No vendor child metric name should appear
    assert "device_poe_power_budget_watts" not in body_lines
    assert "device_psu_temperature_celsius" not in body_lines
    assert "device_temperature_celsius" not in body_lines


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
    assert "label: 'Omnitron'" in common_tsx
    assert "icon: 'mm-omnitron_omnitron'" in common_tsx
    # Brand rule must not match generic technology / object-class terms.
    # Use word-boundary regex so substrings inside other brand names don't
    # falsely trip the assertion.
    brand_rule = (
        common_tsx.lower().split("label: 'omnitron'")[0].split("{ match:")[-1]
    )
    for forbidden in (
        "switch",
        "router",
        "firewall",
        r"\bconverter\b",
        r"\btransceiver\b",
        r"\bfiber\b",
        r"\bmedia\b",
        r"\bpoe\b",
    ):
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
def test_icon_field_uses_object_category_not_brand(metrics):
    """Round 5 icon 铁律: metrics.json icon 字段必须 mm-<object>_<中文>,
    不是 mm-<brand>_<x>. Object category for Switch is mm-switch_交换机;
    brand-specific icon belongs to common.tsx BRANDS[].icon only.
    """
    assert metrics["icon"] == "mm-switch_交换机", (
        f"metrics.json icon must be the Switch category icon "
        f"'mm-switch_交换机' (round 5 iron rule), got {metrics['icon']!r}; "
        f"brand-specific icon belongs to common.tsx BRANDS, not metrics.json."
    )


@pytest.mark.unit
def test_collecttype_uniqueness_in_switch_object():
    """Verify there is exactly one collect_type entry for the Omnitron
    plugin in the switch.tsx collectTypes map (defense against 沉淀 #11
    duplicate keys).
    """
    switch_tsx = (
        WEB_ROOT / "src" / "app" / "monitor" / "hooks" / "integration"
        / "objects" / "networkDevice" / "switch.tsx"
    ).read_text(encoding="utf-8")
    assert switch_tsx.count(f"'{COLLECT_TYPE}'") == 1
    assert switch_tsx.count(f"'{PLUGIN_NAME}'") == 1


@pytest.mark.unit
def test_brand_label_uniqueness_in_common_brands():
    """Verify there is exactly one BRANDS rule for the Omnitron label
    in the common.tsx BRANDS array (defense against 沉淀 #11 duplicate
    keys).
    """
    common_tsx = (WEB_ROOT / "src" / "app" / "monitor" / "utils" / "common.tsx").read_text(
        encoding="utf-8"
    )
    assert common_tsx.count("label: 'Omnitron'") == 1
    assert common_tsx.count("icon: 'mm-omnitron_omnitron'") == 1
