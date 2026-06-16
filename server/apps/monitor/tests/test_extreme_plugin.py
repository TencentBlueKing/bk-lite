"""Contract tests for the Extreme Networks switch SNMP plugin.

Validates the structural contract of Telegraf/snmp_extreme/switch against the
Cisco baseline (Telegraf/snmp_cisco/switch) and the cross-vendor design
decisions recorded for the SNMP brand-plugin family:

* collect_type / config_type / plugin are consistent across metrics.json,
  UI.json, policy.json and the toml template;
* shared device_* metrics keep Cisco's metric_group / unit (so the single
  brand-adaptive dashboard does not mix semantics), and the fan/psu Enum unit
  string is byte-identical to Cisco;
* memory total/free are ordered before the computed memory_usage (otherwise the
  PromQL query-matching shadows the raw series);
* fan/psu states are normalized to the unified 1=normal convention;
* every policy template references a declared metric;
* every metric / metric group / the plugin / the object carry zh-Hans + en
  translations.

OID correctness is intentionally NOT tested here (pending on-site SNMP walk).
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
EXTREME_DIR = PLUGINS / "snmp_extreme" / "switch"
CISCO_DIR = PLUGINS / "snmp_cisco" / "switch"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"

BRAND = "extreme"
COLLECT_TYPE = "snmp_extreme"
CONFIG_TYPE = "extreme"
PLUGIN_NAME = "Switch Extreme SNMP"
OBJECT_NAME = "Switch"

# Units accepted by the product unit system (apps/monitor/utils/unit_converter.py);
# Enum metrics carry a JSON state list as their unit and are handled separately.
SUPPORTED_SCALAR_UNITS = {
    "byteps", "bytes", "counts", "cps", "percent", "celsius", "s", "short", "none",
}


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def metrics():
    return _read_json(EXTREME_DIR / "metrics.json")


@pytest.fixture(scope="module")
def cisco_metrics():
    return _read_json(CISCO_DIR / "metrics.json")


@pytest.fixture(scope="module")
def policy():
    return _read_json(EXTREME_DIR / "policy.json")


@pytest.fixture(scope="module")
def ui():
    return _read_json(EXTREME_DIR / "UI.json")


@pytest.fixture(scope="module")
def toml_text():
    return (EXTREME_DIR / "extreme.child.toml.j2").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def languages():
    return {
        lang: yaml.safe_load((LANGUAGE_DIR / f"{lang}.yaml").read_text(encoding="utf-8"))
        for lang in ("zh-Hans", "en")
    }


# --------------------------------------------------------------------------- #
# cross-file identity: collect_type / config_type / plugin / object
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_collect_type_consistent_across_files(metrics, policy, ui, toml_text):
    assert metrics["status_query"].find(COLLECT_TYPE) != -1
    assert ui["collect_type"] == COLLECT_TYPE
    assert f'collect_type = "{COLLECT_TYPE}"' in toml_text
    # plugin name agreement
    assert metrics["plugin"] == PLUGIN_NAME
    assert policy["plugin"] == PLUGIN_NAME
    # object agreement
    assert metrics["name"] == OBJECT_NAME
    assert ui["object_name"] == OBJECT_NAME
    assert policy["object"] == OBJECT_NAME


@pytest.mark.unit
def test_config_type_consistent(ui, toml_text):
    assert ui["config_type"] == [CONFIG_TYPE]
    assert f'config_type = "{CONFIG_TYPE}"' in toml_text
    assert f'brand = "{BRAND}"' in toml_text


# --------------------------------------------------------------------------- #
# device_* parity with the Cisco baseline (shared dashboard correctness)
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_shared_device_metrics_match_cisco_group_and_unit(metrics, cisco_metrics):
    """Metrics present in BOTH cisco and extreme must keep identical group + unit
    so the single brand-adaptive dashboard does not mix semantics."""
    cisco = {m["name"]: m for m in cisco_metrics["metrics"]}
    drift = []
    for m in metrics["metrics"]:
        base = cisco.get(m["name"])
        if base is None:
            continue
        if m["metric_group"] != base["metric_group"]:
            drift.append(f'{m["name"]}.group {m["metric_group"]}!={base["metric_group"]}')
        if m["unit"] != base["unit"]:
            drift.append(f'{m["name"]}.unit drift')
    assert drift == [], f"device_* drift vs Cisco: {drift}"


@pytest.mark.unit
def test_cpu_query_byte_identical_to_cisco(metrics, cisco_metrics):
    ext = {m["name"]: m for m in metrics["metrics"]}["device_cpu_usage"]
    cis = {m["name"]: m for m in cisco_metrics["metrics"]}["device_cpu_usage"]
    assert ext["query"] == cis["query"]


@pytest.mark.unit
def test_fan_psu_enum_unit_byte_identical_to_cisco(metrics, cisco_metrics):
    ext = {m["name"]: m for m in metrics["metrics"]}
    cis = {m["name"]: m for m in cisco_metrics["metrics"]}
    for name in ("device_fan_state", "device_psu_state"):
        assert ext[name]["data_type"] == "Enum"
        assert ext[name]["unit"] == cis[name]["unit"], f"{name} enum unit drift vs Cisco"
        states = json.loads(ext[name]["unit"])
        normal = [s for s in states if s["name"] == "normal"]
        assert normal and normal[0]["id"] == 1, f"{name} normal must be id=1"


# --------------------------------------------------------------------------- #
# memory model: total/free ordered before computed usage
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_memory_raw_series_ordered_before_usage(metrics):
    order = [m["name"] for m in metrics["metrics"]]
    idx = {n: i for i, n in enumerate(order)}
    assert "device_memory_usage" in idx
    for raw in ("device_memory_total", "device_memory_free"):
        assert raw in idx, f"{raw} missing"
        assert idx[raw] < idx["device_memory_usage"], f"{raw} must precede memory_usage"


@pytest.mark.unit
def test_memory_usage_is_computed_percent(metrics):
    usage = {m["name"]: m for m in metrics["metrics"]}["device_memory_usage"]
    assert usage["unit"] == "percent"
    # extreme has no raw usage series; usage is derived from total + free
    assert "device_memory_total" in usage["query"]
    assert "device_memory_free" in usage["query"]


# --------------------------------------------------------------------------- #
# fan/psu normalization to 1=normal
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_psu_normalized_via_brand_scoped_enum_processor(toml_text):
    """extremePowerSupplyStatus (presentOK=2) is not 1=normal natively, so the
    toml must remap it to 1 with a brand-scoped enum processor."""
    assert "[[processors.enum]]" in toml_text
    assert f'brand = ["{BRAND}"]' in toml_text  # tagpass guards other brands
    assert 'field = "device_psu_state"' in toml_text
    assert '"2" = 1' in toml_text  # presentOK -> normal


@pytest.mark.unit
def test_fan_psu_policy_thresholds_use_gt_one(policy):
    by_metric = {t["metric_name"]: t for t in policy["templates"]}
    for name in ("device_fan_state", "device_psu_state"):
        assert name in by_metric, f"policy missing {name}"
        methods = {th["method"] for th in by_metric[name]["threshold"]}
        values = {th["value"] for th in by_metric[name]["threshold"]}
        assert methods == {">"} and values == {1}, f"{name} must alert on >1"


# --------------------------------------------------------------------------- #
# policy / units / dimensions hygiene
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_policy_templates_reference_existing_metrics(metrics, policy):
    known = {m["name"] for m in metrics["metrics"]}
    bad = [t["metric_name"] for t in policy["templates"] if t["metric_name"] not in known]
    assert bad == [], f"policy references unknown metrics: {bad}"


@pytest.mark.unit
def test_all_metric_units_supported(metrics):
    bad = []
    for m in metrics["metrics"]:
        if m["data_type"] == "Enum":
            continue
        if m["unit"] not in SUPPORTED_SCALAR_UNITS:
            bad.append(f'{m["name"]}:{m["unit"]}')
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
# secrets are never inlined as plaintext
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_passwords_use_template_vars_not_plaintext(toml_text):
    for field in ("auth_password", "priv_password"):
        assert f'{field} = "{{{{ {field} }}}}"' in toml_text, f"{field} must be templated"
