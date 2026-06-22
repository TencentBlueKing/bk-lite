"""Contract tests for the FiberHome (烽火) switch SNMP plugin.

Validates Telegraf/snmp_fiberhome/switch against the Cisco baseline and the
cross-vendor design decisions for the SNMP brand-plugin family.

FiberHome (IANA PEN 3807; WRI-CPU/MEMORY/TEMPERATURE/POWER MIBs) exposes:

  - device_cpu_usage: percent, avg per instance, scaled DOWN by 100 (cpuUsage is
    reported at precision-100, e.g. raw 297 -> 2.97%) (group CPU)
  - device_memory_total/used: bytes (already bytes, NO KB*1024); usage = used/total
    (group Memory)
  - device_temperature_celsius: max per instance (group Temperature)
  - device_psu_state: Enum normalized via processors.enum (raw 0=Normal -> 1=healthy,
    default 2=fault), max per instance (group Hardware Status); policy alerts on >1
  - device_fan_speed: fan RPM, max per instance (group Hardware Status). This is the
    ONLY fan-health signal FiberHome has — its fan exposes no state enum, only speed,
    so fan STATE (device_fan_state) is N/A and must not be modelled.
  - interface_ifHCIn/OutOctets: byte-identical to Cisco

FiberHome reuses the shared Switch CPU/Memory/Temperature/Hardware Status/Traffic
groups; device_fan_speed is a NEW metric name that needs its own i18n. New brand
`fiberhome` adds a common.tsx match + icon.

Regression guard: temperature/psu/fan_speed must live in the *translated* groups,
NOT the untranslated `Environment` group.

OID correctness is intentionally NOT tested here (pending on-site SNMP walk:
cpuUsage precision-100, powerState normal-code 0, memory table index).
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
FH_DIR = PLUGINS / "snmp_fiberhome" / "switch"
CISCO_DIR = PLUGINS / "snmp_cisco" / "switch"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "fiberhome"
COLLECT_TYPE = "snmp_fiberhome"
CONFIG_TYPE = "fiberhome"
INSTANCE_TYPE = "switch"
PLUGIN_NAME = "Switch FiberHome SNMP"
OBJECT_NAME = "Switch"

SUPPORTED_SCALAR_UNITS = {
    "byteps", "bytes", "counts", "cps", "percent", "celsius", "s", "short", "none",
}
INTERFACE_METRICS = ("interface_ifHCInOctets", "interface_ifHCOutOctets")
MEMORY_METRICS = ("device_memory_total", "device_memory_used", "device_memory_usage")
ENUM_METRICS = ("device_psu_state",)
HEALTH_METRICS = (
    "device_cpu_usage", "device_memory_usage", "device_temperature_celsius",
    "device_psu_state", "device_fan_speed",
)
# fan STATE is N/A — FiberHome's fan only exposes speed (RPM), no state enum
ABSENT_METRICS = ("device_fan_state",)


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def metrics():
    return _read_json(FH_DIR / "metrics.json")


@pytest.fixture(scope="module")
def cisco_metrics():
    return _read_json(CISCO_DIR / "metrics.json")


@pytest.fixture(scope="module")
def policy():
    return _read_json(FH_DIR / "policy.json")


@pytest.fixture(scope="module")
def ui():
    return _read_json(FH_DIR / "UI.json")


@pytest.fixture(scope="module")
def toml_text():
    return (FH_DIR / f"{CONFIG_TYPE}.child.toml.j2").read_text(encoding="utf-8")


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
def test_plugin_lives_under_correct_dir():
    assert FH_DIR.parent.name == COLLECT_TYPE
    assert FH_DIR.name == INSTANCE_TYPE


@pytest.mark.unit
def test_toml_filename_follows_convention():
    assert (FH_DIR / f"{CONFIG_TYPE}.child.toml.j2").exists()


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
# health set present; fan STATE absent (only speed)
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_health_metrics_present(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    missing = [h for h in HEALTH_METRICS if h not in names]
    assert missing == [], f"FiberHome health set missing: {missing}"


@pytest.mark.unit
def test_fan_state_not_modelled_only_speed(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    present = [a for a in ABSENT_METRICS if a in names]
    assert present == [], \
        f"FiberHome fan exposes only RPM speed, no state enum; must not model: {present}"
    assert "device_fan_speed" in names, "fan speed (the only fan-health signal) must be modelled"


@pytest.mark.unit
def test_cpu_is_percent_avg_scaled_by_100(metrics):
    cpu = {m["name"]: m for m in metrics["metrics"]}["device_cpu_usage"]
    assert cpu["unit"] == "percent"
    assert cpu["metric_group"] == "CPU"
    assert cpu["dimensions"] == []
    q = cpu["query"].replace(" ", "")
    assert q.startswith("avg(") and "by(instance_id)" in q
    assert "/100" in q, "cpuUsage is precision-100 and must be scaled down by 100"


# --------------------------------------------------------------------------- #
# REGRESSION GUARD: no untranslated `Environment` group
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_no_metric_uses_untranslated_environment_group(metrics):
    offenders = [m["name"] for m in metrics["metrics"] if m["metric_group"] == "Environment"]
    assert offenders == [], (
        "temperature/psu/fan_speed must use translated Temperature / Hardware Status "
        f"groups, not 'Environment': {offenders}"
    )


@pytest.mark.unit
def test_fan_speed_grouped_and_aggregated(metrics):
    fan = {m["name"]: m for m in metrics["metrics"]}["device_fan_speed"]
    assert fan["data_type"] == "Number"
    assert fan["metric_group"] == "Hardware Status"
    assert fan["unit"] in SUPPORTED_SCALAR_UNITS
    assert fan["dimensions"] == []
    q = fan["query"].replace(" ", "")
    assert q.startswith("max(") and "by(instance_id)" in q


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
        if m["name"] not in ENUM_METRICS and m["unit"] != base["unit"]:
            drift.append(f'{m["name"]}.unit')
    assert drift == [], f"shared-metric drift vs Cisco: {drift}"


@pytest.mark.unit
def test_interface_hc_metrics_match_cisco(metrics, cisco_metrics):
    fh = {m["name"]: m for m in metrics["metrics"]}
    cis = {m["name"]: m for m in cisco_metrics["metrics"]}
    for name in INTERFACE_METRICS:
        assert name in fh, f"{name} must be declared"
        for field in ("metric_group", "unit", "query", "dimensions"):
            assert fh[name][field] == cis[name][field], f"{name}.{field} drift vs Cisco"


@pytest.mark.unit
def test_toml_collects_ifhc_counters(toml_text):
    assert "ifHCInOctets" in toml_text and "ifHCOutOctets" in toml_text


# --------------------------------------------------------------------------- #
# memory: total/used bytes (already bytes, NO KB*1024), usage = used/total
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_memory_metrics_present(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    missing = [m for m in MEMORY_METRICS if m not in names]
    assert missing == [], f"memory metrics missing: {missing}"


@pytest.mark.unit
def test_memory_total_and_used_are_raw_bytes(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    for name in ("device_memory_total", "device_memory_used"):
        assert by[name]["unit"] == "bytes", f"{name} must be bytes"
        assert by[name]["metric_group"] == "Memory"
        assert by[name]["dimensions"] == []
        assert "*1024" not in by[name]["query"].replace(" ", ""), \
            f"{name} is already bytes; must NOT scale by 1024"


@pytest.mark.unit
def test_memory_usage_is_used_over_total(metrics):
    usage = {m["name"]: m for m in metrics["metrics"]}["device_memory_usage"]
    assert usage["unit"] == "percent"
    assert usage["metric_group"] == "Memory"
    assert usage["dimensions"] == []
    q = usage["query"].replace(" ", "")
    assert "device_memory_used" in q and "device_memory_total" in q and "/" in q


@pytest.mark.unit
def test_memory_raw_series_ordered_before_usage(metrics):
    order = [m["name"] for m in metrics["metrics"] if m["name"] in MEMORY_METRICS]
    assert order.index("device_memory_used") < order.index("device_memory_usage")
    assert order.index("device_memory_total") < order.index("device_memory_usage")


# --------------------------------------------------------------------------- #
# temperature + psu enum
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
def test_psu_is_normalized_enum(metrics):
    psu = {m["name"]: m for m in metrics["metrics"]}["device_psu_state"]
    assert psu["data_type"] == "Enum"
    assert psu["metric_group"] == "Hardware Status"
    assert psu["dimensions"] == []
    ids = sorted(o["id"] for o in json.loads(psu["unit"]))
    assert ids == [1, 2], f"psu enum must normalize to 1=healthy/2=fault, got {ids}"
    q = psu["query"].replace(" ", "")
    assert q.startswith("max(") and "by(instance_id)" in q


@pytest.mark.unit
def test_toml_has_one_enum_processor_block(toml_text):
    assert toml_text.count("[[processors.enum]]") == 1, "only psu needs normalization"


@pytest.mark.unit
def test_psu_enum_maps_zero_to_healthy(toml_text):
    # powerState raw 0=Normal -> healthy 1; 1/2 fall through to default fault 2
    assert 'namepass = ["device_psu"]' in toml_text
    assert "default = 2" in toml_text
    assert '"0" = 1' in toml_text.replace(" ", "").replace('"0"=1', '"0" = 1') or \
        '"0" = 1' in toml_text


# --------------------------------------------------------------------------- #
# policy / supplementary / units / dimensions hygiene
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_policy_covers_cpu_mem_temp_psu(policy):
    names = {t["metric_name"] for t in policy["templates"]}
    assert names == {
        "device_cpu_usage", "device_memory_usage", "device_temperature_celsius",
        "device_psu_state",
    }, f"FiberHome policy must cover cpu/mem/temp/psu, got {names}"


@pytest.mark.unit
def test_psu_policy_threshold_fault_above_one(policy):
    by = {t["metric_name"]: t for t in policy["templates"]}
    thr = by["device_psu_state"]["threshold"]
    assert any(t["method"] == ">" and t["value"] == 1 for t in thr)


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
# i18n completeness (zh-Hans + en) — incl the NEW device_fan_speed metric
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
def test_new_fan_speed_metric_translated(languages):
    for lang, data in languages.items():
        entry = ((data.get("monitor_object_metric") or {}).get(OBJECT_NAME) or {}).get(
            "device_fan_speed"
        ) or {}
        assert entry.get("name") and entry.get("desc"), \
            f"{lang}: new metric device_fan_speed must be translated"


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
    assert "fiberhome" in text.lower(), "common.tsx must register a FiberHome brand match"


@pytest.mark.unit
def test_brand_icon_asset_present():
    icon = WEB_ROOT / "public" / "assets" / "icons" / "mm-fiberhome_fiberhome.svg"
    assert icon.exists(), "FiberHome brand icon mm-fiberhome_fiberhome.svg must exist"


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
