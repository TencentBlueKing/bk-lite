"""Contract tests for the Korenix switch SNMP plugin.

Validates Telegraf/snmp_korenix/switch against the cross-vendor design
decisions for the SNMP brand-plugin family.

Korenix JetNet (IANA PEN 24062) industrial Ethernet switches are fanless,
passively cooled units whose temperature, dual power-input and relay-alarm
environmental objects live in the vendor private MIB (PEN 24062) and are not
exposed as row-filter-free scalars reachable from a public template. The
private health MIB has no reliable public template, so this is a BASELINE
plugin: it collects only standard MIB-II uptime plus IF-MIB interface metrics
(including the 64-bit ifHC counters) and the device-aggregated traffic totals.
CPU, memory, temperature, fan and power are all N/A and must NOT be modelled,
so there must be NO processors.enum block and NO private PEN-24062 OID.

  - snmp_uptime: baseline uptime (declared as supplementary, re-surfaced here)
  - interface_ifAdminStatus / ifOperStatus: Enum, group Status
  - interface_ifSpeed: bitps, group Bandwidth
  - interface_ifInErrors / ifOutErrors: cps rate, group Packet Error
  - interface_ifInDiscards / ifOutDiscards: cps rate, group Packet Loss
  - interface_ifHCInOctets / ifHCOutOctets: byteps rate, 64-bit, group Traffic
  - device_total_incoming/outgoing_traffic: byteps, group Traffic

Korenix reuses the shared Switch object name, the base switch icon and the
shared switch dashboard, so it needs no brand-specific common.tsx match or icon;
only the switch.tsx collect-type wire is required.

OID correctness is intentionally NOT tested here (pending on-site SNMP walk).
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
KORENIX_DIR = PLUGINS / "snmp" / "switch_korenix"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "korenix"
COLLECT_TYPE = "snmp_korenix"
CONFIG_TYPE = "korenix"
INSTANCE_TYPE = "switch"
PLUGIN_NAME = "Switch Korenix SNMP"
OBJECT_NAME = "Switch"
KORENIX_PEN_ROOT = "1.3.6.1.4.1.24062"

SUPPORTED_SCALAR_UNITS = {
    "byteps", "bytes", "bitps", "counts", "cps", "percent", "celsius", "s", "short", "none",
}
HC_METRICS = ("interface_ifHCInOctets", "interface_ifHCOutOctets")
HEALTH_METRICS = (
    "device_cpu_usage", "device_memory_used", "device_memory_free",
    "device_memory_usage", "device_temperature_celsius",
    "device_fan_state", "device_psu_state",
)


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def metrics():
    return _read_json(KORENIX_DIR / "metrics.json")


@pytest.fixture(scope="module")
def policy():
    return _read_json(KORENIX_DIR / "policy.json")


@pytest.fixture(scope="module")
def ui():
    return _read_json(KORENIX_DIR / "UI.json")


@pytest.fixture(scope="module")
def toml_text():
    return (KORENIX_DIR / "korenix.child.toml.j2").read_text(encoding="utf-8")


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
    assert KORENIX_DIR.parent.name == "snmp"  # 扁平布局


@pytest.mark.unit
def test_toml_filename_follows_convention():
    assert (KORENIX_DIR / f"{CONFIG_TYPE}.child.toml.j2").exists()


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
def test_no_private_health_metrics_modelled(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    present = [h for h in HEALTH_METRICS if h in names]
    assert present == [], \
        f"Korenix baseline plugin must not model private health metrics: {present}"


@pytest.mark.unit
def test_no_enum_processor_block(toml_text):
    assert "[[processors.enum]]" not in toml_text, \
        "Korenix has no fan/psu enum to normalize; no processors.enum expected"


@pytest.mark.unit
def test_no_private_pen_oid_used(toml_text):
    assert KORENIX_PEN_ROOT not in toml_text, \
        "Korenix private PEN 24062 health MIB is not collected in the baseline template"


# --------------------------------------------------------------------------- #
# 64-bit IF-MIB HC traffic
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_hc_metrics_declared_as_byteps_rate(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    for name in HC_METRICS:
        assert name in by, f"{name} must be declared"
        m = by[name]
        assert m["unit"] == "byteps", f"{name} must be byteps"
        assert m["metric_group"] == "Traffic"
        assert m["query"].startswith("rate("), f"{name} must be a rate()"


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
# device-aggregated traffic totals
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_device_total_traffic_aggregated_by_instance(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    for name in ("device_total_incoming_traffic", "device_total_outgoing_traffic"):
        assert name in by, f"{name} must be declared"
        m = by[name]
        assert m["unit"] == "byteps"
        assert m["metric_group"] == "Traffic"
        assert m["dimensions"] == []
        q = m["query"].replace(" ", "")
        assert q.startswith("sum(rate(") and "by(instance_id)" in q


# --------------------------------------------------------------------------- #
# interface status enums normalized to up/down/testing
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_interface_status_metrics_are_enum(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    for name in ("interface_ifAdminStatus", "interface_ifOperStatus"):
        assert name in by, f"{name} must be declared"
        m = by[name]
        assert m["data_type"] == "Enum"
        assert m["metric_group"] == "Status"
        ids = {opt["id"] for opt in json.loads(m["unit"])}
        assert {1, 2}.issubset(ids), f"{name} must expose up(1)/down(2)"


# --------------------------------------------------------------------------- #
# metrics.json hygiene
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_supplementary_indicators_have_no_dangling_refs(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    dangling = [s for s in metrics.get("supplementary_indicators", []) if s not in names]
    assert dangling == [], f"supplementary_indicators reference absent metrics: {dangling}"


@pytest.mark.unit
def test_all_scalar_metric_units_supported(metrics):
    bad = [
        f'{m["name"]}:{m["unit"]}'
        for m in metrics["metrics"]
        if m["data_type"] != "Enum" and m["unit"] not in SUPPORTED_SCALAR_UNITS
    ]
    assert bad == [], f"unsupported units: {bad}"


@pytest.mark.unit
def test_dimensions_well_formed(metrics):
    bad = [
        m["name"]
        for m in metrics["metrics"]
        for d in m.get("dimensions", [])
        if not d.get("name") or not d.get("description")
    ]
    assert bad == [], f"malformed dimensions: {bad}"


# --------------------------------------------------------------------------- #
# policy: error/discard rates only (no health metrics to alert on)
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_policy_templates_reference_existing_metrics(metrics, policy):
    known = {m["name"] for m in metrics["metrics"]}
    bad = [t["metric_name"] for t in policy["templates"] if t["metric_name"] not in known]
    assert bad == [], f"policy references unknown metrics: {bad}"


@pytest.mark.unit
def test_policy_covers_interface_error_and_discard_rates(policy):
    names = {t["metric_name"] for t in policy["templates"]}
    assert names == {
        "interface_ifInErrors", "interface_ifOutErrors",
        "interface_ifInDiscards", "interface_ifOutDiscards",
    }, "Korenix baseline policy must cover interface error/discard rates only"


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
def test_shared_dashboard_no_brand_special_case():
    config_ts = (
        WEB_ROOT / "src" / "app" / "monitor" / "dashboards"
        / "objects" / "switch" / "config.ts"
    )
    assert BRAND not in config_ts.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# secrets never inlined as plaintext
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_passwords_use_template_vars_not_plaintext(toml_text):
    for field in ("auth_password", "priv_password"):
        assert f'{field} = "{{{{ {field} }}}}"' in toml_text, f"{field} must be templated"
