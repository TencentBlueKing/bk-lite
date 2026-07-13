"""Contract tests for the Nokia (ALE OmniSwitch) switch SNMP plugin.

Validates Telegraf/snmp_nokia/switch against the Cisco baseline and the
cross-vendor design decisions for the SNMP brand-plugin family.

Nokia OmniSwitch (formerly Alcatel-Lucent Enterprise, ALCATEL-IND1-HEALTH-MIB /
ALCATEL-IND1-CHASSIS-MIB, IANA PEN 6486) exposes device health directly:
per-module CPU and memory utilization (healthModuleTable, both 0-100 percent),
chassis temperature (chasChassisTemp, celsius) and fan + power-supply state
(chasEntPhysOperStatus). Fan/PSU raw codes are normalized via processors.enum so
up(1) -> 1 (healthy) and everything else -> 2 (fault).

  - device_cpu_usage: avg per instance across modules (percent)
  - device_memory_usage: avg per instance across modules (percent, direct)
  - device_temperature_celsius: max per instance (group Temperature)
  - device_fan_state / device_psu_state: Enum normalized to 1=healthy/2=fault
    (group Hardware Status), max per instance; policy alerts on state > 1
  - interface_ifHCIn/OutOctets: byte-identical Cisco

Nokia reuses the shared Switch metric names + existing Temperature / Hardware
Status groups, so i18n and the shared switch dashboard are already in place. New
brand `nokia` adds a common.tsx match + icon.

OID correctness is intentionally NOT tested here (pending on-site SNMP walk).
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
NOKIA_DIR = PLUGINS / "snmp" / "switch_nokia"
CISCO_DIR = PLUGINS / "snmp" / "switch_cisco"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "nokia"
COLLECT_TYPE = "snmp_nokia"
CONFIG_TYPE = "nokia"
INSTANCE_TYPE = "switch"
PLUGIN_NAME = "Switch Nokia SNMP"
OBJECT_NAME = "Switch"

SUPPORTED_SCALAR_UNITS = {
    "byteps", "bytes", "counts", "cps", "percent", "celsius", "s", "short", "none",
}
INTERFACE_METRICS = ("interface_ifHCInOctets", "interface_ifHCOutOctets")
ENUM_METRICS = ("device_fan_state", "device_psu_state")


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def metrics():
    return _read_json(NOKIA_DIR / "metrics.json")


@pytest.fixture(scope="module")
def cisco_metrics():
    return _read_json(CISCO_DIR / "metrics.json")


@pytest.fixture(scope="module")
def policy():
    return _read_json(NOKIA_DIR / "policy.json")


@pytest.fixture(scope="module")
def ui():
    return _read_json(NOKIA_DIR / "UI.json")


@pytest.fixture(scope="module")
def toml_text():
    return (NOKIA_DIR / "nokia.child.toml.j2").read_text(encoding="utf-8")


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
    assert NOKIA_DIR.parent.name == "snmp"  # 扁平布局:厂商目录直接在 snmp/ 下


@pytest.mark.unit
def test_toml_filename_follows_convention():
    assert (NOKIA_DIR / f"{CONFIG_TYPE}.child.toml.j2").exists()


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
# CPU + interface parity with Cisco (group + unit; CPU query legitimately
# differs because Nokia aggregates the per-module health table)
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
def test_cpu_is_per_module_avg_aggregated_percent(metrics):
    cpu = {m["name"]: m for m in metrics["metrics"]}["device_cpu_usage"]
    assert cpu["unit"] == "percent"
    assert cpu["metric_group"] == "CPU"
    assert cpu["dimensions"] == []
    q = cpu["query"].replace(" ", "")
    assert q.startswith("avg(") and "by(instance_id)" in q


@pytest.mark.unit
def test_memory_usage_is_direct_percent_avg(metrics):
    mem = {m["name"]: m for m in metrics["metrics"]}["device_memory_usage"]
    assert mem["unit"] == "percent"
    assert mem["metric_group"] == "Memory"
    assert mem["dimensions"] == []
    q = mem["query"].replace(" ", "")
    assert q.startswith("avg(") and "by(instance_id)" in q, \
        "Nokia reports memory utilisation directly as percent (healthModuleMemoryLatest)"


@pytest.mark.unit
def test_interface_hc_metrics_match_cisco(metrics, cisco_metrics):
    ext = {m["name"]: m for m in metrics["metrics"]}
    cis = {m["name"]: m for m in cisco_metrics["metrics"]}
    for name in INTERFACE_METRICS:
        assert name in ext, f"{name} must be declared"
        for field in ("metric_group", "unit", "query", "dimensions"):
            assert ext[name][field] == cis[name][field], f"{name}.{field} drift vs Cisco"


# --------------------------------------------------------------------------- #
# environment: temperature + fan + psu (chassis MIB)
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
def test_fan_psu_are_normalized_enum(metrics, name):
    by = {m["name"]: m for m in metrics["metrics"]}
    assert name in by, f"{name} must be declared"
    m = by[name]
    assert m["data_type"] == "Enum"
    assert m["metric_group"] == "Hardware Status"
    assert m["dimensions"] == [], "aggregated state metric must carry no dimension"
    opts = json.loads(m["unit"])
    ids = sorted(o["id"] for o in opts)
    assert ids == [1, 2], f"{name} enum must be normalized to 1=healthy/2=fault, got {ids}"
    q = m["query"].replace(" ", "")
    assert q.startswith("max(") and "by(instance_id)" in q


# --------------------------------------------------------------------------- #
# telegraf enum normalization: two namepass-isolated blocks (fan + psu),
# up(1)->1, default=2
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_toml_has_two_enum_processor_blocks(toml_text):
    assert toml_text.count("[[processors.enum]]") == 2


@pytest.mark.unit
def test_enum_blocks_namepass_isolated_normal_one_fault_default(toml_text):
    assert 'namepass = ["device_fan"]' in toml_text
    assert 'namepass = ["device_psu"]' in toml_text
    assert toml_text.count("default = 2") == 2
    # Nokia raw up(1) maps to healthy 1
    assert '"1" = 1' in toml_text


@pytest.mark.unit
def test_toml_collects_ifhc_counters(toml_text):
    assert "ifHCInOctets" in toml_text and "ifHCOutOctets" in toml_text
    # must NOT fall back to the wrap-prone 32-bit counters
    assert "ifInOctets" not in toml_text and "ifOutOctets" not in toml_text


# --------------------------------------------------------------------------- #
# policy / supplementary / units / dimensions hygiene
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_policy_covers_cpu_mem_temp_fan_psu(policy):
    names = {t["metric_name"] for t in policy["templates"]}
    assert names == {
        "device_cpu_usage", "device_memory_usage",
        "device_temperature_celsius", "device_fan_state", "device_psu_state",
    }, "Nokia policy must cover cpu/mem/temp/fan/psu"


@pytest.mark.unit
@pytest.mark.parametrize("metric", ENUM_METRICS)
def test_state_policy_threshold_fault_above_one(policy, metric):
    by = {t["metric_name"]: t for t in policy["templates"]}
    thr = by[metric]["threshold"]
    assert any(t["method"] == ">" and t["value"] == 1 for t in thr), \
        f"{metric} alert must fire when normalized state > 1"


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
    assert "nokia" in text.lower(), "common.tsx must register a Nokia brand match"


@pytest.mark.unit
def test_brand_icon_asset_present():
    icon = WEB_ROOT / "public" / "assets" / "icons" / "mm-nokia_nokia.svg"
    assert icon.exists(), "Nokia brand icon mm-nokia_nokia.svg must exist"


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
