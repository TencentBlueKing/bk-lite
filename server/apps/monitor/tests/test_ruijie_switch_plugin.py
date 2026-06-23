"""Contract tests for the Ruijie (锐捷) switch SNMP plugin.

Validates Telegraf/snmp_ruijie/switch against the Cisco baseline and the
cross-vendor design decisions for the SNMP brand-plugin family.

Ruijie (IANA PEN 4881; RUIJIE-PROCESS / RUIJIE-MEMORY / RUIJIE-SYSTEM MIBs) is
the most complete switch in the family: it exposes the full device-health set —
CPU, memory, temperature, fan AND power-supply:

  - device_cpu_usage: percent, avg per instance (ruijieNodeCPUTotal5min, group CPU)
  - device_memory_total/used: bytes (KB * 1024); usage = used/total*100 (group Memory)
  - device_temperature_celsius: max per instance (group Temperature)
  - device_fan_state / device_psu_state: Enum normalized via processors.enum to
    1=healthy/2=fault (group Hardware Status), max per instance; policy alerts on
    state > 1
  - interface_ifHCIn/OutOctets: byte-identical to Cisco

Ruijie reuses the shared Switch metric names + the existing CPU / Memory /
Temperature / Hardware Status groups, so the only new i18n is the plugin
name/desc and the shared switch dashboard already lights all 5 health panels.
New brand `ruijie` adds a common.tsx match + icon.

Regression guard: temperature/fan/psu must live in the *translated* groups
Temperature / Hardware Status, NOT the untranslated `Environment` group.

OID correctness is intentionally NOT tested here (pending on-site SNMP walk:
RGOS memory KB unit, multi-slot/multi-sensor temperature, multi-node CPU).
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
RUIJIE_DIR = PLUGINS / "snmp" / "switch_ruijie"
CISCO_DIR = PLUGINS / "snmp" / "switch_cisco"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "ruijie"
COLLECT_TYPE = "snmp_ruijie"
CONFIG_TYPE = "ruijie"
INSTANCE_TYPE = "switch"
PLUGIN_NAME = "Switch Ruijie SNMP"
OBJECT_NAME = "Switch"

SUPPORTED_SCALAR_UNITS = {
    "byteps", "bytes", "counts", "cps", "percent", "celsius", "s", "short", "none",
}
INTERFACE_METRICS = ("interface_ifHCInOctets", "interface_ifHCOutOctets")
MEMORY_METRICS = ("device_memory_total", "device_memory_used", "device_memory_usage")
ENUM_METRICS = ("device_fan_state", "device_psu_state")
HEALTH_METRICS = (
    "device_cpu_usage", "device_memory_usage", "device_temperature_celsius",
    "device_fan_state", "device_psu_state",
)


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def metrics():
    return _read_json(RUIJIE_DIR / "metrics.json")


@pytest.fixture(scope="module")
def cisco_metrics():
    return _read_json(CISCO_DIR / "metrics.json")


@pytest.fixture(scope="module")
def policy():
    return _read_json(RUIJIE_DIR / "policy.json")


@pytest.fixture(scope="module")
def ui():
    return _read_json(RUIJIE_DIR / "UI.json")


@pytest.fixture(scope="module")
def toml_text():
    return (RUIJIE_DIR / f"{CONFIG_TYPE}.child.toml.j2").read_text(encoding="utf-8")


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
    assert RUIJIE_DIR.parent.name == "snmp"  # 扁平布局:厂商目录直接在 snmp/ 下


@pytest.mark.unit
def test_toml_filename_follows_convention():
    assert (RUIJIE_DIR / f"{CONFIG_TYPE}.child.toml.j2").exists()


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
# completeness: all 5 health dimensions present (Ruijie is the full set)
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_all_five_health_metrics_present(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    missing = [h for h in HEALTH_METRICS if h not in names]
    assert missing == [], f"Ruijie must model the full health set; missing: {missing}"


@pytest.mark.unit
def test_cpu_is_percent_avg_aggregated(metrics):
    cpu = {m["name"]: m for m in metrics["metrics"]}["device_cpu_usage"]
    assert cpu["unit"] == "percent"
    assert cpu["metric_group"] == "CPU"
    assert cpu["dimensions"] == []
    q = cpu["query"].replace(" ", "")
    assert q.startswith("avg(") and "by(instance_id)" in q


# --------------------------------------------------------------------------- #
# REGRESSION GUARD: env metrics must use translated groups, not `Environment`
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_no_metric_uses_untranslated_environment_group(metrics):
    offenders = [m["name"] for m in metrics["metrics"] if m["metric_group"] == "Environment"]
    assert offenders == [], (
        "temperature/fan/psu must use the translated Temperature / Hardware Status "
        f"groups, not the untranslated 'Environment' group: {offenders}"
    )


# --------------------------------------------------------------------------- #
# parity with Cisco (group + unit byte-identity on shared metrics)
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
        # enum units legitimately differ (processors.enum normalized to 2 values)
        if m["name"] not in ENUM_METRICS and m["unit"] != base["unit"]:
            drift.append(f'{m["name"]}.unit')
    assert drift == [], f"shared-metric drift vs Cisco: {drift}"


@pytest.mark.unit
def test_interface_hc_metrics_match_cisco(metrics, cisco_metrics):
    rj = {m["name"]: m for m in metrics["metrics"]}
    cis = {m["name"]: m for m in cisco_metrics["metrics"]}
    for name in INTERFACE_METRICS:
        assert name in rj, f"{name} must be declared"
        for field in ("metric_group", "unit", "query", "dimensions"):
            assert rj[name][field] == cis[name][field], f"{name}.{field} drift vs Cisco"


@pytest.mark.unit
def test_toml_collects_ifhc_counters(toml_text):
    assert "ifHCInOctets" in toml_text and "ifHCOutOctets" in toml_text


# --------------------------------------------------------------------------- #
# memory: total/used bytes (KB*1024), usage = used/total
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_memory_metrics_present(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    missing = [m for m in MEMORY_METRICS if m not in names]
    assert missing == [], f"memory metrics missing: {missing}"


@pytest.mark.unit
def test_memory_total_and_used_are_bytes(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    for name in ("device_memory_total", "device_memory_used"):
        assert by[name]["unit"] == "bytes", f"{name} must be bytes"
        assert by[name]["metric_group"] == "Memory"
        assert by[name]["dimensions"] == []
        assert "*1024" in by[name]["query"].replace(" ", ""), \
            f"{name} must convert KB to bytes (*1024)"


@pytest.mark.unit
def test_memory_usage_is_used_over_total(metrics):
    usage = {m["name"]: m for m in metrics["metrics"]}["device_memory_usage"]
    assert usage["unit"] == "percent"
    assert usage["metric_group"] == "Memory"
    assert usage["dimensions"] == []
    q = usage["query"].replace(" ", "")
    assert "device_memory_used" in q and "device_memory_total" in q and "/" in q, \
        "memory_usage must be used / total"


@pytest.mark.unit
def test_memory_raw_series_ordered_before_usage(metrics):
    order = [m["name"] for m in metrics["metrics"] if m["name"] in MEMORY_METRICS]
    assert order.index("device_memory_used") < order.index("device_memory_usage"), \
        "raw used must precede computed usage so its query is not shadowed"
    assert order.index("device_memory_total") < order.index("device_memory_usage")


# --------------------------------------------------------------------------- #
# temperature + fan + psu (both enums)
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_temperature_is_celsius_max_aggregated(metrics):
    t = {m["name"]: m for m in metrics["metrics"]}["device_temperature_celsius"]
    assert t["unit"] == "celsius"
    assert t["metric_group"] == "Temperature"
    assert t["dimensions"] == []
    q = t["query"].replace(" ", "")
    assert q.startswith("max(") and "by(instance_id)" in q


@pytest.mark.unit
@pytest.mark.parametrize("name", ENUM_METRICS)
def test_fan_psu_are_normalized_enums(metrics, name):
    by = {m["name"]: m for m in metrics["metrics"]}
    m = by[name]
    assert m["data_type"] == "Enum"
    assert m["metric_group"] == "Hardware Status"
    assert m["dimensions"] == [], "aggregated enum metric must carry no dimension"
    opts = json.loads(m["unit"])
    ids = sorted(o["id"] for o in opts)
    assert ids == [1, 2], f"{name} enum must normalize to 1=healthy/2=fault, got {ids}"
    q = m["query"].replace(" ", "")
    assert q.startswith("max(") and "by(instance_id)" in q


@pytest.mark.unit
def test_toml_has_two_enum_processor_blocks(toml_text):
    assert toml_text.count("[[processors.enum]]") == 2


@pytest.mark.unit
def test_enum_blocks_namepass_isolated_with_fault_default(toml_text):
    assert 'namepass = ["device_fan"]' in toml_text
    assert 'namepass = ["device_psu"]' in toml_text
    assert toml_text.count("default = 2") == 2
    # raw 1=noexist / 3=ready / 4=normal map to healthy 1; 2/5/6 fall through to fault 2
    for code in ('"1" = 1', '"3" = 1', '"4" = 1'):
        assert code in toml_text, f"missing healthy mapping {code}"


# --------------------------------------------------------------------------- #
# policy / supplementary / units / dimensions hygiene
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_policy_covers_all_five_health_metrics(policy):
    names = {t["metric_name"] for t in policy["templates"]}
    assert names == set(HEALTH_METRICS), \
        f"Ruijie policy must cover the full health set, got {names}"


@pytest.mark.unit
@pytest.mark.parametrize("name", ENUM_METRICS)
def test_enum_policy_threshold_fault_above_one(policy, name):
    by = {t["metric_name"]: t for t in policy["templates"]}
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
# i18n completeness (zh-Hans + en)
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
# frontend wiring
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
    assert "ruijie" in text.lower(), "common.tsx must register a Ruijie brand match"


@pytest.mark.unit
def test_brand_icon_asset_present():
    icon = WEB_ROOT / "public" / "assets" / "icons" / "mm-ruijie_ruijie.svg"
    assert icon.exists(), "Ruijie brand icon mm-ruijie_ruijie.svg must exist"


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
