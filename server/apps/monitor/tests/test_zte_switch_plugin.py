"""Contract tests for the ZTE ZXR10 switch SNMP plugin.

Validates Telegraf/snmp_zte/switch against the Cisco baseline and the
cross-vendor design decisions for the SNMP brand-plugin family.

ZTE ZXR10 (IANA PEN 3902; ZXR10-MIB zxr10System unit table) is a slim switch:
its system MIB exposes only per-unit CPU and a direct percent-used memory value,
plus standard IF-MIB 64-bit HC interface counters:

  - device_cpu_usage: percent, avg per instance (zxr10SystemCpuUtility5m, group CPU)
  - device_memory_usage: percent, read DIRECTLY (zxr10SystemMemUsed) — a single
    series, NO total/free/used byte pool (group Memory)
  - interface_ifHCIn/OutOctets: byte-identical to Cisco

Temperature / fan / power-supply are N/A and must NOT be modelled: the ZXR10-MIB
system table has no sensor objects (ZTE environment sensors live in
ZTE-AN-ENVMON-MIB for the access-node/OLT line, which is row/model-specific and
not the ZXR10 switch). Because there are no fan/psu enums, the toml carries no
processors.enum block, and the shared switch dashboard's temp/fan/psu panels
render "--" for ZTE (correct).

ZTE reuses the shared Switch metric names + the existing CPU / Memory / Traffic
groups, so the only new i18n is the plugin name/desc. New brand `zte` adds a
common.tsx match + icon.

OID correctness is intentionally NOT tested here (pending on-site SNMP walk —
the LibreNMS test snmprec carries no zxr10System table data, so the zxr10System
unit OIDs / MemUsed-is-percent assumption are the most in need of on-site walk).
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
ZTE_DIR = PLUGINS / "snmp" / "switch_zte"
CISCO_DIR = PLUGINS / "snmp" / "switch_cisco"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "zte"
COLLECT_TYPE = "snmp_zte"
CONFIG_TYPE = "zte"
INSTANCE_TYPE = "switch"
PLUGIN_NAME = "Switch ZTE SNMP"
OBJECT_NAME = "Switch"

SUPPORTED_SCALAR_UNITS = {
    "byteps", "bytes", "counts", "cps", "percent", "celsius", "s", "short", "none",
}
INTERFACE_METRICS = ("interface_ifHCInOctets", "interface_ifHCOutOctets")
PRESENT_METRICS = ("device_cpu_usage", "device_memory_usage")
# the full sensor/byte-pool set ZTE does NOT model
ABSENT_METRICS = (
    "device_temperature_celsius", "device_fan_state", "device_psu_state",
    "device_memory_total", "device_memory_free", "device_memory_used",
)


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def metrics():
    return _read_json(ZTE_DIR / "metrics.json")


@pytest.fixture(scope="module")
def cisco_metrics():
    return _read_json(CISCO_DIR / "metrics.json")


@pytest.fixture(scope="module")
def policy():
    return _read_json(ZTE_DIR / "policy.json")


@pytest.fixture(scope="module")
def ui():
    return _read_json(ZTE_DIR / "UI.json")


@pytest.fixture(scope="module")
def toml_text():
    return (ZTE_DIR / f"{CONFIG_TYPE}.child.toml.j2").read_text(encoding="utf-8")


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
    assert ZTE_DIR.parent.name == "snmp"  # 扁平布局:厂商目录直接在 snmp/ 下


@pytest.mark.unit
def test_toml_filename_follows_convention():
    assert (ZTE_DIR / f"{CONFIG_TYPE}.child.toml.j2").exists()


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
# present metrics: CPU + Memory (both percent), nothing else health-wise
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_cpu_and_memory_present(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    missing = [m for m in PRESENT_METRICS if m not in names]
    assert missing == [], f"CPU/memory must be modelled; missing: {missing}"


@pytest.mark.unit
def test_cpu_is_percent_avg_aggregated(metrics):
    cpu = {m["name"]: m for m in metrics["metrics"]}["device_cpu_usage"]
    assert cpu["unit"] == "percent"
    assert cpu["metric_group"] == "CPU"
    assert cpu["dimensions"] == []
    q = cpu["query"].replace(" ", "")
    assert q.startswith("avg(") and "by(instance_id)" in q


@pytest.mark.unit
def test_memory_is_direct_percent_single_series(metrics):
    mem = {m["name"]: m for m in metrics["metrics"]}["device_memory_usage"]
    assert mem["unit"] == "percent"
    assert mem["metric_group"] == "Memory"
    assert mem["dimensions"] == []
    q = mem["query"].replace(" ", "")
    # direct percent-used: a single device_memory_usage series, no total/free math
    assert q.startswith("avg(") and "by(instance_id)" in q
    assert "device_memory_total" not in q and "device_memory_free" not in q
    assert "/" not in q.split("device_memory_usage", 1)[-1].split("}")[0]


# --------------------------------------------------------------------------- #
# N/A: temperature / fan / psu / byte-pool memory must NOT be modelled
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_sensors_and_byte_pool_not_modelled(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    present = [a for a in ABSENT_METRICS if a in names]
    assert present == [], \
        f"ZXR10-MIB has no sensors and no byte-pool; must not model: {present}"


@pytest.mark.unit
def test_no_metric_uses_untranslated_environment_group(metrics):
    offenders = [m["name"] for m in metrics["metrics"] if m["metric_group"] == "Environment"]
    assert offenders == [], f"must not use untranslated 'Environment' group: {offenders}"


@pytest.mark.unit
def test_toml_has_no_enum_processor_block(toml_text):
    assert "[[processors.enum]]" not in toml_text, \
        "ZTE has no fan/psu enum to normalize"


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
        if m["unit"] != base["unit"]:
            drift.append(f'{m["name"]}.unit')
    assert drift == [], f"shared-metric drift vs Cisco: {drift}"


@pytest.mark.unit
def test_interface_hc_metrics_match_cisco(metrics, cisco_metrics):
    zte = {m["name"]: m for m in metrics["metrics"]}
    cis = {m["name"]: m for m in cisco_metrics["metrics"]}
    for name in INTERFACE_METRICS:
        assert name in zte, f"{name} must be declared"
        for field in ("metric_group", "unit", "query", "dimensions"):
            assert zte[name][field] == cis[name][field], f"{name}.{field} drift vs Cisco"


@pytest.mark.unit
def test_toml_collects_ifhc_counters(toml_text):
    assert "ifHCInOctets" in toml_text and "ifHCOutOctets" in toml_text


# --------------------------------------------------------------------------- #
# policy / supplementary / units / dimensions hygiene
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_policy_covers_cpu_and_memory_only(policy):
    names = {t["metric_name"] for t in policy["templates"]}
    assert names == set(PRESENT_METRICS), \
        f"ZTE policy must cover cpu/mem only (no N/A sensors), got {names}"


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
def test_supplementary_indicators_do_not_reference_na_sensors(metrics):
    supp = set(metrics.get("supplementary_indicators", []))
    leaked = [a for a in ABSENT_METRICS if a in supp]
    assert leaked == [], f"N/A metrics must not appear in supplementary_indicators: {leaked}"


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
    assert "zte" in text.lower(), "common.tsx must register a ZTE brand match"


@pytest.mark.unit
def test_brand_icon_asset_present():
    icon = WEB_ROOT / "public" / "assets" / "icons" / "mm-zte_zte.svg"
    assert icon.exists(), "ZTE brand icon mm-zte_zte.svg must exist"


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
