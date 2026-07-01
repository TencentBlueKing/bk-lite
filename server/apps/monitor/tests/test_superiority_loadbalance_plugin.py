"""Contract tests for the Superiority loadbalance SNMP plugin.

Superiority (超数) reuses the Foundry/Brocade private tree (IANA PEN 1991) and
exposes two scalar health OIDs only:
  - CPU  snAgGblCpuUtil1SecAvg 1.3.6.1.4.1.1991.1.1.2.1.50.0  (direct %)
  - mem  snAgGblDynMemUtil     1.3.6.1.4.1.1991.1.1.2.1.53.0  (direct %)
Both are scalar OIDs and MUST carry the .0 instance suffix. Memory is reported
directly as a percentage (no used/free bytes), so the plugin declares
device_memory_usage ONLY — there must be NO device_memory_used /
device_memory_free. No connections/temperature/fan/PSU OIDs (all N/A; lb_current_connections
is dropped vs the loadbalance baseline because the 1991 tree has no such OID), so there must
be NO processors.enum block.
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
BRAND_DIR = PLUGINS / "snmp" / "loadbalance_superiority"
BASE_DIR = PLUGINS / "snmp" / "loadbalance_a10"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "superiority"
COLLECT_TYPE = "snmp_superiority"
CONFIG_TYPE = "superiority"
INSTANCE_TYPE = "loadbalance"
PLUGIN_NAME = "Loadbalance Superiority SNMP"
OBJECT_NAME = "Loadbalance"
PEN_ROOT = "1.3.6.1.4.1.1991"
CPU_OID = "1.3.6.1.4.1.1991.1.1.2.1.50.0"
MEM_OID = "1.3.6.1.4.1.1991.1.1.2.1.53.0"

SUPPORTED_SCALAR_UNITS = {
    "byteps", "bytes", "counts", "cps", "percent", "celsius", "s", "short",
    "none", "bitps",
}
ABSENT_METRICS = (
    "device_memory_used", "device_memory_free",
    "device_fan_state", "device_psu_state", "device_temperature_celsius",
    "lb_current_connections",
)


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def metrics():
    return _read_json(BRAND_DIR / "metrics.json")


@pytest.fixture(scope="module")
def base_metrics():
    return _read_json(BASE_DIR / "metrics.json")


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
def test_plugin_lives_under_correct_dir(metrics):
    assert metrics["collect_type"] == COLLECT_TYPE
    assert BRAND_DIR.parent.name == "snmp"


@pytest.mark.unit
def test_toml_filename_follows_convention():
    assert (BRAND_DIR / f"{CONFIG_TYPE}.child.toml.j2").exists()


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


@pytest.mark.unit
def test_shared_metrics_match_baseline_group_and_unit(metrics, base_metrics):
    base = {m["name"]: m for m in base_metrics["metrics"]}
    drift = []
    for m in metrics["metrics"]:
        b = base.get(m["name"])
        if b is None:
            continue
        if m["metric_group"] != b["metric_group"]:
            drift.append(f'{m["name"]}.group')
        if m["unit"] != b["unit"]:
            drift.append(f'{m["name"]}.unit')
    assert drift == [], f"shared-metric drift vs Firewall baseline: {drift}"


@pytest.mark.unit
def test_cpu_is_percent_in_loadbalance_group(metrics):
    cpu = {m["name"]: m for m in metrics["metrics"]}["device_cpu_usage"]
    assert cpu["unit"] == "percent"
    assert cpu["metric_group"] == "Loadbalance"
    assert cpu["dimensions"] == []


@pytest.mark.unit
def test_memory_usage_is_direct_percent(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    assert "device_memory_usage" in by
    mu = by["device_memory_usage"]
    assert mu["unit"] == "percent"
    assert mu["dimensions"] == []
    q = mu["query"].replace(" ", "")
    assert "device_memory_used" not in q and "device_memory_free" not in q


@pytest.mark.unit
def test_no_used_free_temp_fan_psu(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    present = [a for a in ABSENT_METRICS if a in names]
    assert present == [], f"Superiority has no used/free/conn OIDs; must not model: {present}"


@pytest.mark.unit
def test_no_enum_processor_block(toml_text):
    assert "[[processors.enum]]" not in toml_text


@pytest.mark.unit
def test_private_oids_under_pen_1991_with_scalar_suffix(toml_text):
    assert CPU_OID in toml_text  # CPU scalar .0
    assert MEM_OID in toml_text  # mem usage scalar .0
    assert PEN_ROOT in toml_text


@pytest.mark.unit
def test_health_oids_carry_scalar_zero_suffix(toml_text):
    # critical: scalar health OIDs taken as table.field without .0 silently
    # walk a subtree and return no value
    for oid in (CPU_OID, MEM_OID):
        assert oid.endswith(".0"), f"{oid} missing scalar .0 suffix"
        assert oid in toml_text


@pytest.mark.unit
def test_toml_collects_64bit_ifhc_counters(toml_text):
    assert "1.3.6.1.2.1.31.1.1.1.6" in toml_text
    assert "1.3.6.1.2.1.31.1.1.1.10" in toml_text
    assert "ifHCInOctets" in toml_text and "ifHCOutOctets" in toml_text


@pytest.mark.unit
def test_cpu_memory_tables_rename_to_usage(toml_text):
    assert 'name = "device_cpu"' in toml_text
    assert 'name = "device_memory"' in toml_text
    assert 'name = "usage"' in toml_text


@pytest.mark.unit
def test_policy_templates_reference_existing_metrics(metrics, policy):
    known = {m["name"] for m in metrics["metrics"]}
    bad = [t["metric_name"] for t in policy["templates"] if t["metric_name"] not in known]
    assert bad == [], f"policy references unknown metrics: {bad}"


@pytest.mark.unit
def test_policy_covers_cpu_and_memory(policy):
    names = {t["metric_name"] for t in policy["templates"]}
    assert "device_cpu_usage" in names
    assert "device_memory_usage" in names


@pytest.mark.unit
def test_supplementary_indicators_have_no_dangling_refs(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    dangling = [
        s for s in metrics.get("supplementary_indicators", [])
        if s not in names and s != "snmp_uptime"
    ]
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
def test_frontend_collecttype_wired_to_loadbalance_object():
    tsx = (
        WEB_ROOT / "src" / "app" / "monitor" / "hooks" / "integration"
        / "objects" / "networkDevice" / "loadbalance.tsx"
    )
    assert f"'{PLUGIN_NAME}': '{COLLECT_TYPE}'" in tsx.read_text(encoding="utf-8")


@pytest.mark.unit
def test_frontend_brand_match_registered():
    common = WEB_ROOT / "src" / "app" / "monitor" / "utils" / "common.tsx"
    assert "superiority" in common.read_text(encoding="utf-8").lower()


@pytest.mark.unit
def test_brand_icon_asset_present():
    icon = WEB_ROOT / "public" / "assets" / "icons" / "mm-superiority_superiority.svg"
    assert icon.exists()


@pytest.mark.unit
def test_passwords_use_template_vars_not_plaintext(toml_text):
    for field in ("auth_password", "priv_password"):
        assert f'{field} = "{{{{ {field} }}}}"' in toml_text
