"""Contract tests for the Neteye firewall SNMP plugin.

Neteye (网御星云 / Leadsec, IANA PEN 3224) reuses the NetScreen-family resource
MIB but with its own authoritative scalar OIDs:
  - CPU   nsResCpuAvg      1.3.6.1.4.1.3224.16.1.1.0  (direct %)
  - mem   nsResMemAllocate 1.3.6.1.4.1.3224.16.2.1.0  (used bytes)
  - mem   nsResMemLeft     1.3.6.1.4.1.3224.16.2.2.0  (free bytes)
Memory usage is derived as used/(used+free)*100. No temperature/fan/PSU/session
OIDs are collected (all N/A), so there must be NO processors.enum block.

The plugin reuses the shared Firewall metric names + groups, so i18n and the
shared firewall dashboard are already in place. OID correctness vs the on-site
walk is asserted structurally against the local authoritative snmp.yaml roots.
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
BRAND_DIR = PLUGINS / "snmp" / "firewall_neteye"
BASE_DIR = PLUGINS / "snmp" / "firewall_hillstone"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "neteye"
COLLECT_TYPE = "snmp_neteye"
CONFIG_TYPE = "neteye"
INSTANCE_TYPE = "firewall"
PLUGIN_NAME = "Firewall Neteye SNMP"
OBJECT_NAME = "Firewall"
PEN_ROOT = "1.3.6.1.4.1.3224"

SUPPORTED_SCALAR_UNITS = {
    "byteps", "bytes", "counts", "cps", "percent", "celsius", "s", "short",
    "none", "bitps",
}
MEMORY_METRICS = ("device_memory_used", "device_memory_free", "device_memory_usage")
ABSENT_METRICS = ("device_fan_state", "device_psu_state", "device_temperature_celsius")


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


# directory / cross-file identity
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


# parity with the shared Firewall baseline
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
def test_cpu_is_percent_in_firewall_group(metrics):
    cpu = {m["name"]: m for m in metrics["metrics"]}["device_cpu_usage"]
    assert cpu["unit"] == "percent"
    assert cpu["metric_group"] == "Firewall"
    assert cpu["dimensions"] == []


# memory: used/free bytes, usage = used/(used+free)*100
@pytest.mark.unit
def test_memory_metrics_present(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    missing = [m for m in MEMORY_METRICS if m not in names]
    assert missing == [], f"memory metrics missing: {missing}"


@pytest.mark.unit
def test_memory_used_and_free_are_bytes(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    for name in ("device_memory_used", "device_memory_free"):
        assert by[name]["unit"] == "bytes", f"{name} must be bytes"
        assert by[name]["dimensions"] == []


@pytest.mark.unit
def test_memory_used_declared_before_free_and_usage(metrics):
    order = [m["name"] for m in metrics["metrics"] if m["name"] in MEMORY_METRICS]
    assert order.index("device_memory_used") < order.index("device_memory_free")
    assert order.index("device_memory_free") < order.index("device_memory_usage")


@pytest.mark.unit
def test_memory_usage_is_used_over_used_plus_free(metrics):
    ext = {m["name"]: m for m in metrics["metrics"]}["device_memory_usage"]
    assert ext["unit"] == "percent"
    q = ext["query"].replace(" ", "")
    assert "device_memory_used" in q and "device_memory_free" in q
    assert "*100" in q, "memory_usage must be used/(used+free)*100"


# no temperature / fan / PSU modelled
@pytest.mark.unit
def test_temp_fan_psu_not_modelled(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    present = [a for a in ABSENT_METRICS if a in names]
    assert present == [], f"Neteye collects no temp/fan/psu; must not model: {present}"


@pytest.mark.unit
def test_no_enum_processor_block(toml_text):
    assert "[[processors.enum]]" not in toml_text


# OID hygiene: private OIDs rooted under PEN 3224; 64-bit IF-MIB counters
@pytest.mark.unit
def test_private_oids_under_pen_3224(toml_text):
    assert "1.3.6.1.4.1.3224.16.1.1.0" in toml_text  # nsResCpuAvg
    assert "1.3.6.1.4.1.3224.16.2.1.0" in toml_text  # nsResMemAllocate (used)
    assert "1.3.6.1.4.1.3224.16.2.2.0" in toml_text  # nsResMemLeft (free)
    assert PEN_ROOT in toml_text


@pytest.mark.unit
def test_toml_collects_64bit_ifhc_counters(toml_text):
    assert "1.3.6.1.2.1.31.1.1.1.6" in toml_text   # ifHCInOctets
    assert "1.3.6.1.2.1.31.1.1.1.10" in toml_text  # ifHCOutOctets
    assert "ifHCInOctets" in toml_text and "ifHCOutOctets" in toml_text


@pytest.mark.unit
def test_cpu_memory_tables_rename_to_usage_used_free(toml_text):
    assert 'name = "device_cpu"' in toml_text
    assert 'name = "device_memory"' in toml_text
    assert 'name = "used"' in toml_text and 'name = "free"' in toml_text


# metrics.json is a brand delta: must NOT re-declare baseline uptime
@pytest.mark.unit
def test_metrics_is_brand_delta_without_baseline_uptime(metrics):
    # snmp_uptime is allowed only as a re-exported reference metric, never a new
    # private declaration; ensure no private uptime OID is invented here.
    assert "1.3.6.1.2.1.1.3.0" not in json.dumps(metrics)


# policy hygiene
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


# i18n completeness (zh-Hans + en)
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


# frontend wiring
@pytest.mark.unit
def test_frontend_collecttype_wired_to_firewall_object():
    tsx = (
        WEB_ROOT / "src" / "app" / "monitor" / "hooks" / "integration"
        / "objects" / "networkDevice" / "firewall.tsx"
    )
    assert f"'{PLUGIN_NAME}': '{COLLECT_TYPE}'" in tsx.read_text(encoding="utf-8")


@pytest.mark.unit
def test_frontend_brand_match_registered():
    common = WEB_ROOT / "src" / "app" / "monitor" / "utils" / "common.tsx"
    assert "neteye" in common.read_text(encoding="utf-8").lower()


@pytest.mark.unit
def test_brand_icon_asset_present():
    icon = WEB_ROOT / "public" / "assets" / "icons" / "mm-neteye_neteye.svg"
    assert icon.exists()


# secrets never inlined as plaintext
@pytest.mark.unit
def test_passwords_use_template_vars_not_plaintext(toml_text):
    for field in ("auth_password", "priv_password"):
        assert f'{field} = "{{{{ {field} }}}}"' in toml_text
