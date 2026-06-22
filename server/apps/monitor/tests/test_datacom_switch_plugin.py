"""Contract tests for the Datacom DmOS switch SNMP plugin.

Validates Telegraf/snmp_datacom/switch against the Cisco baseline and the
cross-vendor design decisions for the SNMP brand-plugin family.

Datacom DmOS (DMOS-SYSMON-MIB, IANA PEN 3709) exposes device health as two
table subtrees only: per-slot CPU load (cpuLoadOneMinuteActive) and system
memory (used/total bytes). So this is a CPU + Memory profile with NO
temperature / fan / psu metric and NO enum processor — the DmOS SYSMON MIB has
no sensor objects (temperature lives only in the legacy, incompatible
DMswitch-MIB). Like every switch vendor it still exposes the 64-bit ifHC
interface counters.

Two legitimate variants vs the simplest scalar vendors:
  - device_cpu_usage is a per-slot TABLE, so it is averaged per instance
    (avg(...) by (instance_id)) rather than a bare scalar like Cisco.
  - device_memory_usage uses the sum(used)/sum(total)*100 branch3 formula
    (byte-identical to mikrotik) because DmOS memory is table-valued.

Datacom reuses the shared Switch metric names, so i18n and the shared switch
dashboard are already in place — no new i18n family, no dashboard change.

OID correctness is intentionally NOT tested here (pending on-site SNMP walk).
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
DATACOM_DIR = PLUGINS / "snmp_datacom" / "switch"
CISCO_DIR = PLUGINS / "snmp_cisco" / "switch"
MIKROTIK_DIR = PLUGINS / "snmp_mikrotik" / "switch"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "datacom"
COLLECT_TYPE = "snmp_datacom"
CONFIG_TYPE = "datacom"
INSTANCE_TYPE = "switch"
PLUGIN_NAME = "Switch Datacom SNMP"
OBJECT_NAME = "Switch"

SUPPORTED_SCALAR_UNITS = {
    "byteps", "bytes", "counts", "cps", "percent", "celsius", "s", "short", "none",
}
INTERFACE_METRICS = ("interface_ifHCInOctets", "interface_ifHCOutOctets")
MEMORY_METRICS = ("device_memory_used", "device_memory_total", "device_memory_usage")
ABSENT_METRICS = (
    "device_temperature_celsius", "device_fan_state", "device_psu_state",
)


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def metrics():
    return _read_json(DATACOM_DIR / "metrics.json")


@pytest.fixture(scope="module")
def cisco_metrics():
    return _read_json(CISCO_DIR / "metrics.json")


@pytest.fixture(scope="module")
def mikrotik_metrics():
    return _read_json(MIKROTIK_DIR / "metrics.json")


@pytest.fixture(scope="module")
def policy():
    return _read_json(DATACOM_DIR / "policy.json")


@pytest.fixture(scope="module")
def ui():
    return _read_json(DATACOM_DIR / "UI.json")


@pytest.fixture(scope="module")
def toml_text():
    return (DATACOM_DIR / "datacom.child.toml.j2").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def languages():
    return {
        lang: yaml.safe_load((LANGUAGE_DIR / f"{lang}.yaml").read_text(encoding="utf-8"))
        for lang in ("zh-Hans", "en")
    }


# --------------------------------------------------------------------------- #
# directory / cross-file identity (collect_type / config_type / instance_type)
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_plugin_lives_under_correct_dir():
    assert DATACOM_DIR.parent.name == COLLECT_TYPE
    assert DATACOM_DIR.name == INSTANCE_TYPE


@pytest.mark.unit
def test_toml_filename_follows_convention():
    assert (DATACOM_DIR / f"{CONFIG_TYPE}.child.toml.j2").exists()


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


@pytest.mark.unit
def test_object_is_switch_not_other_type(metrics):
    assert metrics["name"] == "Switch"
    assert all("instance_type='switch'" in m["query"] or "{" not in m["query"]
               for m in metrics["metrics"])


# --------------------------------------------------------------------------- #
# reduced profile: CPU + Memory + interface, no temp/fan/psu, no enum
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_reduced_profile_absent_metrics(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    present = [a for a in ABSENT_METRICS if a in names]
    assert present == [], f"unexpected metrics for a CPU+Memory-only vendor: {present}"


@pytest.mark.unit
def test_no_enum_processor_in_toml(toml_text):
    assert "[[processors.enum]]" not in toml_text


@pytest.mark.unit
def test_policy_only_cpu_and_memory(policy):
    names = {t["metric_name"] for t in policy["templates"]}
    assert names == {"device_cpu_usage", "device_memory_usage"}


@pytest.mark.unit
def test_supplementary_indicators_have_no_dangling_refs(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    dangling = [s for s in metrics.get("supplementary_indicators", []) if s not in names]
    assert dangling == [], f"supplementary_indicators reference absent metrics: {dangling}"


# --------------------------------------------------------------------------- #
# device_* / interface parity with the Cisco baseline (group + unit; queries
# may legitimately differ where DmOS aggregates table-valued sources)
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_shared_device_metrics_match_cisco_group_and_unit(metrics, cisco_metrics):
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
    assert drift == [], f"device_*/interface drift vs Cisco: {drift}"


@pytest.mark.unit
def test_cpu_is_per_slot_avg_aggregated_percent(metrics):
    cpu = {m["name"]: m for m in metrics["metrics"]}["device_cpu_usage"]
    assert cpu["unit"] == "percent"
    assert cpu["metric_group"] == "CPU"
    assert cpu["dimensions"] == []
    q = cpu["query"].replace(" ", "")
    assert q.startswith("avg(") and "by(instance_id)" in q, \
        "DmOS CPU is per-slot and must be averaged per instance"


# --------------------------------------------------------------------------- #
# memory model: table-valued used/total, usage = branch3 (byte-identical mikrotik)
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_memory_metrics_present(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    missing = [m for m in MEMORY_METRICS if m not in names]
    assert missing == [], f"memory metrics missing: {missing}"


@pytest.mark.unit
def test_memory_used_and_total_are_bytes(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    for name in ("device_memory_used", "device_memory_total"):
        assert by[name]["unit"] == "bytes", f"{name} must be bytes"
        assert by[name]["metric_group"] == "Memory"


@pytest.mark.unit
def test_memory_usage_is_used_over_total_branch3(metrics, mikrotik_metrics):
    ext = {m["name"]: m for m in metrics["metrics"]}["device_memory_usage"]
    ref = {m["name"]: m for m in mikrotik_metrics["metrics"]}["device_memory_usage"]
    assert ext["unit"] == "percent"
    assert ext["query"] == ref["query"], "memory_usage must match the branch3 used/total formula"


# --------------------------------------------------------------------------- #
# interface 64-bit HC counters — byte-identical to Cisco
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_interface_hc_metrics_present_and_match_cisco(metrics, cisco_metrics):
    ext = {m["name"]: m for m in metrics["metrics"]}
    cis = {m["name"]: m for m in cisco_metrics["metrics"]}
    for name in INTERFACE_METRICS:
        assert name in ext, f"{name} must be declared"
        for field in ("metric_group", "unit", "query", "dimensions"):
            assert ext[name][field] == cis[name][field], f"{name}.{field} drift vs Cisco"


@pytest.mark.unit
def test_toml_collects_ifhc_counters(toml_text):
    assert "ifHCInOctets" in toml_text and "ifHCOutOctets" in toml_text


# --------------------------------------------------------------------------- #
# policy / units / dimensions hygiene
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_policy_templates_reference_existing_metrics(metrics, policy):
    known = {m["name"] for m in metrics["metrics"]}
    bad = [t["metric_name"] for t in policy["templates"] if t["metric_name"] not in known]
    assert bad == [], f"policy references unknown metrics: {bad}"


@pytest.mark.unit
def test_no_dangling_descr_in_alert_names(policy):
    for t in policy["templates"]:
        assert "${metric_descr}" not in t["alert_name"], f"{t['metric_name']} dangling descr"


@pytest.mark.unit
def test_all_metric_units_supported(metrics):
    bad = [
        f'{m["name"]}:{m["unit"]}'
        for m in metrics["metrics"]
        if m["data_type"] != "Enum" and m["unit"] not in SUPPORTED_SCALAR_UNITS
    ]
    assert bad == [], f"unsupported units: {bad}"


@pytest.mark.unit
def test_scalar_metrics_have_no_descr_dimension(metrics):
    """CPU and memory scalars must not carry a per-sensor descr dimension."""
    by = {m["name"]: m for m in metrics["metrics"]}
    for name in ("device_cpu_usage",) + MEMORY_METRICS:
        assert by[name]["dimensions"] == [], f"{name} should have no dimensions"


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
# i18n completeness (zh-Hans + en) — shared Switch metric names, already present
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
# frontend wiring: collectType maps to the switch object, brand match + icon
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
    assert "datacom" in text.lower(), "common.tsx must register a Datacom brand match"


@pytest.mark.unit
def test_brand_icon_asset_present():
    icon = WEB_ROOT / "public" / "assets" / "icons" / "mm-datacom_datacom.svg"
    assert icon.exists(), "Datacom brand icon mm-datacom_datacom.svg must exist"


@pytest.mark.unit
def test_memory_model_needs_no_config_ts_change():
    """branch3 (used/total) is computed in metrics.json; the shared dashboard
    reads device_memory_usage uniformly, so config.ts must not special-case
    this brand (zero regression)."""
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
