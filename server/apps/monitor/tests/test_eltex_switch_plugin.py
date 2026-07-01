"""Contract tests for the Eltex MES switch SNMP plugin.

Validates Telegraf/snmp_eltex/switch against the Cisco baseline and the
cross-vendor design decisions for the SNMP brand-plugin family.

Eltex MES (RADLAN/Marvell-based MIBs + ELTEX private OIDs, IANA PEN 89/35265) is
the FIRST switch brand to collect real temperature / fan / PSU, because Eltex
exposes them as dedicated typed value columns (rlPhdUnitEnvParamTempSensorValue,
rlEnvMonFanState, rlPhdUnitEnvParamMainPSStatus) rather than the mixed
ENTITY-SENSOR table that needs per-row filtering. So unlike hphpn/datacom this
vendor has an Environment health profile on top of CPU + Memory + interface:

  - device_cpu_usage: scalar rlCpuUtilDuringLast5Minutes (byte-identical Cisco)
  - device_memory_total/free: bytes; usage = (total-free)/total*100
  - device_temperature_celsius: max per instance (group Temperature)
  - device_fan_state / device_psu_state: Enum normalized via telegraf
    processors.enum to 1=healthy / 2=fault, max per instance (group
    Hardware Status); the shared dashboard convention is 1=normal, >1=fault.

Fan/PSU raw codes are normalized in two namepass-isolated processors.enum
blocks (default=2). Because the metric query aggregates max() by (instance_id),
the enum metrics carry NO dimension (regression guard for the fan_state
fanName-dimension fix). Eltex reuses the shared Switch metric names + the
existing Temperature / Hardware Status groups, so i18n and the shared switch
dashboard (which already has temp/fan/psu panels) are already in place — Eltex
is simply the first vendor to light them up. New brand `eltex` adds a
common.tsx match + icon.

OID correctness is intentionally NOT tested here (pending on-site SNMP walk).
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
ELTEX_DIR = PLUGINS / "snmp" / "switch_eltex"
CISCO_DIR = PLUGINS / "snmp" / "switch_cisco"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "eltex"
COLLECT_TYPE = "snmp_eltex"
CONFIG_TYPE = "eltex"
INSTANCE_TYPE = "switch"
PLUGIN_NAME = "Switch Eltex SNMP"
OBJECT_NAME = "Switch"

SUPPORTED_SCALAR_UNITS = {
    "byteps", "bytes", "counts", "cps", "percent", "celsius", "s", "short", "none",
}
INTERFACE_METRICS = ("interface_ifHCInOctets", "interface_ifHCOutOctets")
MEMORY_METRICS = ("device_memory_total", "device_memory_free", "device_memory_usage")
ENV_METRICS = ("device_temperature_celsius", "device_fan_state", "device_psu_state")
ENUM_METRICS = ("device_fan_state", "device_psu_state")


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def metrics():
    return _read_json(ELTEX_DIR / "metrics.json")


@pytest.fixture(scope="module")
def cisco_metrics():
    return _read_json(CISCO_DIR / "metrics.json")


@pytest.fixture(scope="module")
def policy():
    return _read_json(ELTEX_DIR / "policy.json")


@pytest.fixture(scope="module")
def ui():
    return _read_json(ELTEX_DIR / "UI.json")


@pytest.fixture(scope="module")
def toml_text():
    return (ELTEX_DIR / "eltex.child.toml.j2").read_text(encoding="utf-8")


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
    assert metrics["collect_type"] == COLLECT_TYPE  # 身份来自 metrics.json,不依赖目录(#3590 解耦)
    assert ELTEX_DIR.parent.name == "snmp"  # 扁平布局:厂商目录直接在 snmp/ 下


@pytest.mark.unit
def test_toml_filename_follows_convention():
    assert (ELTEX_DIR / f"{CONFIG_TYPE}.child.toml.j2").exists()


@pytest.mark.unit
def test_collect_type_consistent_across_files(metrics, policy, ui, toml_text):
    assert COLLECT_TYPE in metrics["status_query"]
    assert f"instance_type='{INSTANCE_TYPE}'" in metrics["status_query"]
    assert ui["collect_type"] == COLLECT_TYPE
    assert f'collect_type = "{COLLECT_TYPE}"' in toml_text
    assert f'instance_type = "{{{{ instance_type }}}}"' in toml_text
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
# CPU + interface parity with the Cisco baseline
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_shared_metrics_match_cisco_group_and_unit(metrics, cisco_metrics):
    cisco = {m["name"]: m for m in cisco_metrics["metrics"]}
    drift = []
    for m in metrics["metrics"]:
        base = cisco.get(m["name"])
        if base is None:
            continue
        if m["metric_group"] != base["metric_group"]:
            drift.append(f'{m["name"]}.group')
        # fan/psu units legitimately differ: Eltex normalizes the raw codes via
        # processors.enum to a 2-value 1=healthy/2=fault enum, so its enum domain
        # is intentionally smaller than Cisco's raw multi-value enum. Compare unit
        # only for non-normalized metrics.
        if m["name"] not in ENUM_METRICS and m["unit"] != base["unit"]:
            drift.append(f'{m["name"]}.unit')
    assert drift == [], f"shared-metric drift vs Cisco: {drift}"


@pytest.mark.unit
def test_cpu_query_byte_identical_to_cisco(metrics, cisco_metrics):
    ext = {m["name"]: m for m in metrics["metrics"]}["device_cpu_usage"]
    cis = {m["name"]: m for m in cisco_metrics["metrics"]}["device_cpu_usage"]
    assert ext["query"] == cis["query"]
    assert ext["dimensions"] == []


@pytest.mark.unit
def test_interface_hc_metrics_match_cisco(metrics, cisco_metrics):
    ext = {m["name"]: m for m in metrics["metrics"]}
    cis = {m["name"]: m for m in cisco_metrics["metrics"]}
    for name in INTERFACE_METRICS:
        assert name in ext, f"{name} must be declared"
        for field in ("metric_group", "unit", "query", "dimensions"):
            assert ext[name][field] == cis[name][field], f"{name}.{field} drift vs Cisco"


# --------------------------------------------------------------------------- #
# memory: total/free bytes, usage = (total-free)/total
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_memory_metrics_present(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    missing = [m for m in MEMORY_METRICS if m not in names]
    assert missing == [], f"memory metrics missing: {missing}"


@pytest.mark.unit
def test_memory_total_and_free_are_bytes(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    for name in ("device_memory_total", "device_memory_free"):
        assert by[name]["unit"] == "bytes", f"{name} must be bytes"
        assert by[name]["metric_group"] == "Memory"
        assert by[name]["dimensions"] == []


@pytest.mark.unit
def test_memory_usage_is_total_minus_free_over_total(metrics):
    usage = {m["name"]: m for m in metrics["metrics"]}["device_memory_usage"]
    assert usage["unit"] == "percent"
    assert usage["dimensions"] == []
    q = usage["query"].replace(" ", "")
    assert "device_memory_total" in q and "device_memory_free" in q and "-" in q, \
        "memory_usage must be (total - free) / total"


# --------------------------------------------------------------------------- #
# Environment: temperature + fan/psu (first switch with real sensors)
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_environment_metrics_present(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    missing = [m for m in ENV_METRICS if m not in names]
    assert missing == [], f"environment metrics missing: {missing}"


@pytest.mark.unit
def test_temperature_is_celsius_max_aggregated(metrics):
    t = {m["name"]: m for m in metrics["metrics"]}["device_temperature_celsius"]
    assert t["unit"] == "celsius"
    assert t["metric_group"] == "Temperature"
    assert t["dimensions"] == []
    q = t["query"].replace(" ", "")
    assert q.startswith("max(") and "by(instance_id)" in q


@pytest.mark.unit
def test_fan_and_psu_are_normalized_enums(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    for name in ENUM_METRICS:
        m = by[name]
        assert m["data_type"] == "Enum", f"{name} must be Enum"
        assert m["metric_group"] == "Hardware Status"
        opts = json.loads(m["unit"])
        ids = sorted(o["id"] for o in opts)
        assert ids == [1, 2], f"{name} enum must be normalized to 1=healthy/2=fault, got {ids}"
        q = m["query"].replace(" ", "")
        assert q.startswith("max(") and "by(instance_id)" in q, \
            f"{name} must be aggregated max per instance"


@pytest.mark.unit
def test_enum_metrics_have_no_dimension(metrics):
    """Regression guard: the enum metrics aggregate max() by (instance_id),
    which drops any per-sensor label, so they must NOT declare a dimension
    (the fan_state fanName dimension was removed in review)."""
    by = {m["name"]: m for m in metrics["metrics"]}
    for name in ENUM_METRICS:
        assert by[name]["dimensions"] == [], \
            f"{name} aggregates per instance and must carry no dimension"


# --------------------------------------------------------------------------- #
# telegraf enum normalization: two namepass-isolated blocks, default=2
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_toml_has_two_enum_processor_blocks(toml_text):
    assert toml_text.count("[[processors.enum]]") == 2


@pytest.mark.unit
def test_enum_blocks_are_namepass_isolated_with_fault_default(toml_text):
    assert 'namepass = ["device_fan"]' in toml_text
    assert 'namepass = ["device_psu"]' in toml_text
    # both normalization blocks must default unknown codes to fault (2)
    assert toml_text.count("default = 2") == 2
    # healthy code 1 maps to 1
    assert '"1" = 1' in toml_text


@pytest.mark.unit
def test_toml_collects_ifhc_counters(toml_text):
    assert "ifHCInOctets" in toml_text and "ifHCOutOctets" in toml_text


# --------------------------------------------------------------------------- #
# policy / supplementary / units / dimensions hygiene
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_policy_covers_cpu_mem_temp_fan_psu(policy):
    names = {t["metric_name"] for t in policy["templates"]}
    assert names == {
        "device_cpu_usage", "device_memory_usage",
        "device_temperature_celsius", "device_fan_state", "device_psu_state",
    }


@pytest.mark.unit
def test_fan_psu_policy_thresholds_fault_above_one(policy):
    by = {t["metric_name"]: t for t in policy["templates"]}
    for name in ENUM_METRICS:
        thr = by[name]["threshold"]
        assert any(t["method"] == ">" and t["value"] == 1 for t in thr), \
            f"{name} alert must fire when normalized state > 1"


@pytest.mark.unit
def test_policy_templates_reference_existing_metrics(metrics, policy):
    known = {m["name"] for m in metrics["metrics"]}
    bad = [t["metric_name"] for t in policy["templates"] if t["metric_name"] not in known]
    assert bad == [], f"policy references unknown metrics: {bad}"


@pytest.mark.unit
def test_supplementary_indicators_have_no_dangling_refs(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    dangling = [s for s in metrics.get("supplementary_indicators", []) if s not in names]
    assert dangling == [], f"supplementary_indicators reference absent metrics: {dangling}"


@pytest.mark.unit
def test_no_dangling_descr_in_alert_names(policy):
    for t in policy["templates"]:
        assert "${metric_descr}" not in t["alert_name"], f"{t['metric_name']} dangling descr"


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
# i18n completeness (zh-Hans + en) — reuses shared Switch names + groups
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_plugin_has_bilingual_name_and_desc(languages):
    for lang, data in languages.items():
        entry = (data.get("monitor_object_plugin") or {}).get(PLUGIN_NAME) or {}
        assert entry.get("name"), f"{lang}: plugin name missing"
        assert entry.get("desc"), f"{lang}: plugin desc missing"


@pytest.mark.unit
def test_every_metric_has_bilingual_translation(metrics, languages):
    missing = []
    for lang, data in languages.items():
        group = (data.get("monitor_object_metric") or {}).get(OBJECT_NAME) or {}
        for m in metrics["metrics"]:
            entry = group.get(m["name"]) or {}
            if not entry.get("name") or not entry.get("desc"):
                missing.append(f'{lang}:{m["name"]}')
    assert missing == [], f"metrics missing translation: {missing}"


@pytest.mark.unit
def test_every_metric_group_has_bilingual_translation(metrics, languages):
    groups = {m["metric_group"] for m in metrics["metrics"]}
    missing = []
    for lang, data in languages.items():
        trans = (data.get("monitor_object_metric_group") or {}).get(OBJECT_NAME) or {}
        missing += [f"{lang}:{g}" for g in groups if not trans.get(g)]
    assert missing == [], f"metric groups missing translation: {missing}"


@pytest.mark.unit
def test_object_has_bilingual_translation(languages):
    for lang, data in languages.items():
        obj = (data.get("monitor_object") or {}).get(OBJECT_NAME)
        assert obj, f"{lang}: object {OBJECT_NAME} missing translation"


# --------------------------------------------------------------------------- #
# frontend wiring: collectType → switch object, brand match + icon
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
def test_frontend_brand_match_registered():
    common = WEB_ROOT / "src" / "app" / "monitor" / "utils" / "common.tsx"
    text = common.read_text(encoding="utf-8")
    assert "eltex" in text.lower(), "common.tsx must register an Eltex brand match"


@pytest.mark.unit
def test_brand_icon_asset_present():
    icon = WEB_ROOT / "public" / "assets" / "icons" / "mm-eltex_eltex.svg"
    assert icon.exists(), "Eltex brand icon mm-eltex_eltex.svg must exist"


@pytest.mark.unit
def test_shared_dashboard_has_env_panels_and_no_brand_special_case():
    """The shared switch dashboard already carries temperature/fan/psu panels;
    Eltex is the first vendor to populate them, so config.ts must not
    special-case this brand."""
    config_ts = (
        WEB_ROOT / "src" / "app" / "monitor" / "dashboards"
        / "objects" / "switch" / "config.ts"
    )
    text = config_ts.read_text(encoding="utf-8")
    assert BRAND not in text
    for name in ENV_METRICS:
        assert name in text, f"shared switch dashboard should already panel {name}"


# --------------------------------------------------------------------------- #
# secrets never inlined as plaintext
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_passwords_use_template_vars_not_plaintext(toml_text):
    for field in ("auth_password", "priv_password"):
        assert f'{field} = "{{{{ {field} }}}}"' in toml_text, f"{field} must be templated"
