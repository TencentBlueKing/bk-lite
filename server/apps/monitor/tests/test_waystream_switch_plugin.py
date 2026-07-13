"""Contract tests for the Waystream switch SNMP plugin.

Validates Telegraf/snmp_waystream/switch against the cross-vendor design
decisions for the SNMP brand-plugin family.

Waystream FTTH/ASR switches (IANA PEN 9303) have a verified WAYSTREAM-SMI /
WAYSTREAM-RPM-MIB enterprise tree, but the available state only confirms IPTV
QoS / RPM objects and does not provide row-filter-free scalar device-health
gauges. This is therefore a zero-delta child plugin: metrics.json declares no
vendor-specific metrics. The shared Switch SNMP floor supplies uptime, IF-MIB
interface metrics, 64-bit ifHC counters and device-aggregated traffic totals.
CPU, memory, temperature, fan and power are all N/A and must NOT be modelled,
so there must be NO processors.enum block and NO private PEN 9303 OID.

Waystream reuses the shared Switch object name and dashboard but has a
brand-specific common.tsx match and icon, plus the switch.tsx collect-type wire.

OID correctness is intentionally NOT tested here (pending on-site SNMP walk).
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
WAYSTREAM_DIR = PLUGINS / "snmp" / "switch_waystream"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "waystream"
COLLECT_TYPE = "snmp_waystream"
CONFIG_TYPE = "waystream"
INSTANCE_TYPE = "switch"
PLUGIN_NAME = "Switch Waystream SNMP"
OBJECT_NAME = "Switch"
WAYSTREAM_PEN_ROOT = "1.3.6.1.4.1.9303"

HEALTH_METRICS = (
    "device_cpu_usage", "device_memory_used", "device_memory_free",
    "device_memory_usage", "device_temperature_celsius",
    "device_fan_state", "device_psu_state",
)
BASE_METRICS = {
    "snmp_uptime",
    "interface_ifAdminStatus", "interface_ifOperStatus", "interface_ifSpeed",
    "interface_ifInErrors", "interface_ifOutErrors",
    "interface_ifInDiscards", "interface_ifOutDiscards",
    "interface_ifInUcastPkts", "interface_ifOutUcastPkts",
    "interface_ifInOctets", "interface_ifOutOctets",
    "interface_ifHCInOctets", "interface_ifHCOutOctets",
    "device_total_incoming_traffic", "device_total_outgoing_traffic",
}


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def metrics():
    return _read_json(WAYSTREAM_DIR / "metrics.json")


@pytest.fixture(scope="module")
def policy():
    return _read_json(WAYSTREAM_DIR / "policy.json")


@pytest.fixture(scope="module")
def ui():
    return _read_json(WAYSTREAM_DIR / "UI.json")


@pytest.fixture(scope="module")
def toml_text():
    return (WAYSTREAM_DIR / "waystream.child.toml.j2").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def languages():
    return {
        lang: yaml.safe_load((LANGUAGE_DIR / f"{lang}.yaml").read_text(encoding="utf-8"))
        for lang in ("zh-Hans", "en")
    }


# --------------------------------------------------------------------------- #
# directory / cross-file identity
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_plugin_lives_under_correct_dir(metrics):
    assert metrics["collect_type"] == COLLECT_TYPE
    assert WAYSTREAM_DIR.parent.name == "snmp"  # 扁平布局


@pytest.mark.unit
def test_toml_filename_follows_convention():
    assert (WAYSTREAM_DIR / f"{CONFIG_TYPE}.child.toml.j2").exists()


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
    assert not any(f["name"] == "brand" for f in ui["form_fields"])


# --------------------------------------------------------------------------- #
# baseline plugin: NO private health metrics, NO enum, NO private PEN OID
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_metrics_json_is_zero_delta_child(metrics):
    assert metrics["metrics"] == []
    assert metrics["supplementary_indicators"] == []


@pytest.mark.unit
def test_metrics_json_does_not_redeclare_snmp_floor(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    leaked = sorted(names & BASE_METRICS)
    assert leaked == [], f"SNMP floor metrics must stay in generic snmp/switch only: {leaked}"


@pytest.mark.unit
def test_no_private_health_metrics_modelled(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    present = [h for h in HEALTH_METRICS if h in names]
    assert present == [], \
        f"Waystream baseline plugin must not model private health metrics: {present}"


@pytest.mark.unit
def test_no_enum_processor_block(toml_text):
    assert "[[processors.enum]]" not in toml_text, \
        "Waystream has no fan/psu enum to normalize; no processors.enum expected"


@pytest.mark.unit
def test_no_private_pen_oid_used(toml_text):
    assert WAYSTREAM_PEN_ROOT not in toml_text, \
        "Waystream private PEN 9303 tree is not collected in the baseline template"


# --------------------------------------------------------------------------- #
# 64-bit IF-MIB HC traffic remains in the Telegraf child template
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_toml_collects_64bit_ifhc_counters(toml_text):
    assert "1.3.6.1.2.1.31.1.1.1.6" in toml_text  # ifHCInOctets
    assert "1.3.6.1.2.1.31.1.1.1.10" in toml_text  # ifHCOutOctets
    assert "ifHCInOctets" in toml_text and "ifHCOutOctets" in toml_text


@pytest.mark.unit
def test_toml_collects_iftable_and_uptime(toml_text):
    assert "1.3.6.1.2.1.1.3.0" in toml_text  # sysUpTime
    assert "1.3.6.1.2.1.2.2" in toml_text     # ifTable


# --------------------------------------------------------------------------- #
# metrics.json hygiene
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_supplementary_indicators_have_no_dangling_refs(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    dangling = [s for s in metrics.get("supplementary_indicators", []) if s not in names]
    assert dangling == [], f"supplementary_indicators reference absent metrics: {dangling}"


# --------------------------------------------------------------------------- #
# policy: no vendor metrics, so no brand-level policy templates
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_policy_templates_reference_existing_metrics(metrics, policy):
    known = {m["name"] for m in metrics["metrics"]}
    bad = [t["metric_name"] for t in policy["templates"] if t["metric_name"] not in known]
    assert bad == [], f"policy references unknown metrics: {bad}"


@pytest.mark.unit
def test_policy_has_no_brand_level_templates(policy):
    assert policy["templates"] == []


# --------------------------------------------------------------------------- #
# i18n completeness (zh-Hans + en)
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_plugin_has_bilingual_name_and_desc(languages):
    for lang, data in languages.items():
        entry = (data.get("monitor_object_plugin") or {}).get(PLUGIN_NAME) or {}
        assert entry.get("name"), f"{lang}: plugin name missing"
        assert entry.get("desc"), f"{lang}: plugin desc missing"


@pytest.mark.unit
def test_en_desc_has_no_halfwidth_colon_space(languages):
    en = (languages["en"].get("monitor_object_plugin") or {}).get(PLUGIN_NAME) or {}
    assert ": " not in en.get("desc", ""), \
        "en desc must avoid half-width ': ' (use em dash or full-width colon)"


# --------------------------------------------------------------------------- #
# frontend wiring: only the switch.tsx collect-type wire is required
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_frontend_collecttype_wired_to_switch_object():
    switch_tsx = (
        WEB_ROOT / "src" / "app" / "monitor" / "hooks" / "integration"
        / "objects" / "networkDevice" / "switch.tsx"
    )
    text = switch_tsx.read_text(encoding="utf-8")
    assert f"'{PLUGIN_NAME}': '{COLLECT_TYPE}'" in text


@pytest.mark.unit
def test_brand_match_present_in_common():
    common = WEB_ROOT / "src" / "app" / "monitor" / "utils" / "common.tsx"
    assert BRAND in common.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# secrets never inlined as plaintext
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_passwords_use_template_vars_not_plaintext(toml_text):
    for field in ("auth_password", "priv_password"):
        assert f'{field} = "{{{{ {field} }}}}"' in toml_text, f"{field} must be templated"
