"""Contract tests for the Alaxala switch SNMP plugin.

Alaxala Networks AX-series managed switches expose device health under the
private AlaxalA-MIB box-management table (IANA PEN 21839). For the AX2430S
family the counters live at 1.3.6.1.4.1.21839.2.2.6.2.1.2.1.<col>.<member>:

  - device_cpu_usage   : axsCpuLoad1m       (.11, direct %)  — max() aggregated
  - device_memory_used : axsMemoryUsedSize  (.8, bytes)      — max() aggregated
  - device_memory_free : axsMemoryFreeSize  (.9, bytes)      — max() aggregated
  - device_memory_usage: derived used/(used+free)*100

The columns are indexed per stack/chassis member; the real value lives on the
active member while standby rows report zero, hence max() aggregation. The box
management table exposes only a discrete temperature status enum
(axsTemperatureStatusNumber), not a pollable Celsius value, and no numeric
fan/psu state object, so temperature, fan and power are N/A and must NOT be
modelled (no processors.enum block).

OID values are pending on-site SNMP walk; only the PEN root and structural
contract are asserted here.
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
BRAND_DIR = PLUGINS / "snmp" / "switch_alaxala"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "alaxala"
COLLECT_TYPE = "snmp_alaxala"
CONFIG_TYPE = "alaxala"
INSTANCE_TYPE = "switch"
PLUGIN_NAME = "Switch Alaxala SNMP"
OBJECT_NAME = "Switch"
PEN_ROOT = "1.3.6.1.4.1.21839"

SUPPORTED_SCALAR_UNITS = {
    "byteps", "bytes", "bitps", "counts", "cps", "percent", "celsius", "s", "short", "none",
}
HC_METRICS = ("interface_ifHCInOctets", "interface_ifHCOutOctets")
MAX_AGG_METRICS = ("device_cpu_usage", "device_memory_used", "device_memory_free")


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def metrics():
    return _read_json(BRAND_DIR / "metrics.json")


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


# --------------------------------------------------------------------------- #
# directory / cross-file identity
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_plugin_lives_under_correct_dir(metrics):
    assert metrics["collect_type"] == COLLECT_TYPE
    assert BRAND_DIR.parent.name == "snmp"  # 扁平布局


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


# --------------------------------------------------------------------------- #
# PEN correctness: Alaxala 21839
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_uses_alaxala_pen(toml_text):
    assert PEN_ROOT in toml_text, "Alaxala AX series uses IANA PEN 21839"


# --------------------------------------------------------------------------- #
# health metrics: max()-aggregated CPU + memory used/free, derived usage
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_max_aggregated_health_metrics(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    for name in MAX_AGG_METRICS:
        assert name in by, f"{name} must be declared"
        m = by[name]
        q = m["query"].replace(" ", "")
        assert q.startswith("max(") and "by(instance_id)" in q, \
            f"{name} must be max()-aggregated by instance_id (real value on active member)"
        assert m["dimensions"] == [], f"{name} aggregates away dimensions"


@pytest.mark.unit
def test_memory_usage_derived_from_used_and_free(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    assert "device_memory_usage" in by
    q = by["device_memory_usage"]["query"].replace(" ", "")
    assert "device_memory_used" in q and "device_memory_free" in q, \
        "memory usage must be derived from used/(used+free)"
    assert "*100" in q
    assert by["device_memory_usage"]["dimensions"] == []


@pytest.mark.unit
def test_cpu_and_memory_usage_are_percent(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    assert by["device_cpu_usage"]["unit"] == "percent"
    assert by["device_memory_usage"]["unit"] == "percent"
    assert by["device_memory_used"]["unit"] == "bytes"
    assert by["device_memory_free"]["unit"] == "bytes"


@pytest.mark.unit
def test_no_enum_processor_block(toml_text):
    assert "[[processors.enum]]" not in toml_text, \
        "Alaxala temperature/fan/psu are N/A; no enum normalization expected"


@pytest.mark.unit
def test_temperature_fan_psu_not_modelled(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    assert "device_temperature_celsius" not in names, \
        "AX box-management exposes only a temperature status enum, not a Celsius value"
    assert "device_fan_state" not in names
    assert "device_psu_state" not in names


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
        assert m["query"].startswith("rate(")


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
# policy: CPU + memory usage alerting only
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_policy_templates_reference_existing_metrics(metrics, policy):
    known = {m["name"] for m in metrics["metrics"]}
    bad = [t["metric_name"] for t in policy["templates"] if t["metric_name"] not in known]
    assert bad == [], f"policy references unknown metrics: {bad}"


@pytest.mark.unit
def test_policy_covers_cpu_and_memory(policy):
    names = {t["metric_name"] for t in policy["templates"]}
    assert names == {"device_cpu_usage", "device_memory_usage"}


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
# frontend wiring: switch.tsx collect-type wire + common.tsx brand match
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
