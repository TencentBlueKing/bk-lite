"""Contract tests for the Alcatel-Lucent (Nokia/TiMOS) switch SNMP plugin.

Validates Telegraf/snmp_alcatel/switch against the Cisco baseline and the
cross-vendor design decisions for the SNMP brand-plugin family.

Alcatel-Lucent reports system memory as a used/free byte pool
(TIMETRA-CHASSIS-MIB sgiMemoryUsed / sgiMemoryAvailable) — the same shape as
Cisco — so device_memory_usage is the byte-identical computed used/(used+free)
expression and the shared brand-adaptive dashboard hits its branch-2 with zero
config change. Temperature is per-sensor (tmnxHwName descr), but fan/psu tables
(TmnxDeviceState, native 3=deviceStateOk) expose no descr name column, so those
two metrics must declare no descr dimension and their alert templates must not
reference ${metric_descr}. Both fan and psu are normalized to 1=normal via a
brand-scoped enum processor.

OID correctness is intentionally NOT tested here (pending on-site SNMP walk).
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
ALCATEL_DIR = PLUGINS / "snmp" / "switch_alcatel"
CISCO_DIR = PLUGINS / "snmp" / "switch_cisco"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"

BRAND = "alcatel"
COLLECT_TYPE = "snmp_alcatel"
CONFIG_TYPE = "alcatel"
PLUGIN_NAME = "Switch Alcatel-Lucent SNMP"
OBJECT_NAME = "Switch"

SUPPORTED_SCALAR_UNITS = {
    "byteps", "bytes", "counts", "cps", "percent", "celsius", "s", "short", "none",
}


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def metrics():
    return _read_json(ALCATEL_DIR / "metrics.json")


@pytest.fixture(scope="module")
def cisco_metrics():
    return _read_json(CISCO_DIR / "metrics.json")


@pytest.fixture(scope="module")
def policy():
    return _read_json(ALCATEL_DIR / "policy.json")


@pytest.fixture(scope="module")
def ui():
    return _read_json(ALCATEL_DIR / "UI.json")


@pytest.fixture(scope="module")
def toml_text():
    return (ALCATEL_DIR / "alcatel.child.toml.j2").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def languages():
    return {
        lang: yaml.safe_load((LANGUAGE_DIR / f"{lang}.yaml").read_text(encoding="utf-8"))
        for lang in ("zh-Hans", "en")
    }


# --------------------------------------------------------------------------- #
# cross-file identity
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_collect_type_consistent_across_files(metrics, policy, ui, toml_text):
    assert COLLECT_TYPE in metrics["status_query"]
    assert ui["collect_type"] == COLLECT_TYPE
    assert f'collect_type = "{COLLECT_TYPE}"' in toml_text
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
# device_* parity with the Cisco baseline (byte-pool memory => identical)
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
    assert drift == [], f"device_* drift vs Cisco: {drift}"


@pytest.mark.unit
def test_cpu_and_memory_usage_queries_byte_identical_to_cisco(metrics, cisco_metrics):
    ext = {m["name"]: m for m in metrics["metrics"]}
    cis = {m["name"]: m for m in cisco_metrics["metrics"]}
    for name in ("device_cpu_usage", "device_memory_usage"):
        assert ext[name]["query"] == cis[name]["query"], f"{name} query drift vs Cisco"


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
# byte-pool memory: used/free ordered before computed usage
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_memory_used_free_ordered_before_usage(metrics):
    order = [m["name"] for m in metrics["metrics"]]
    idx = {n: i for i, n in enumerate(order)}
    for raw in ("device_memory_used", "device_memory_free"):
        assert raw in idx, f"{raw} missing"
        assert idx[raw] < idx["device_memory_usage"], f"{raw} must precede memory_usage"


@pytest.mark.unit
def test_memory_usage_is_computed_from_used_and_free(metrics):
    usage = {m["name"]: m for m in metrics["metrics"]}["device_memory_usage"]
    assert usage["unit"] == "percent"
    assert "device_memory_used" in usage["query"]
    assert "device_memory_free" in usage["query"]


# --------------------------------------------------------------------------- #
# fan/psu normalization to 1=normal (TmnxDeviceState 3=Ok -> 1)
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_fan_and_psu_normalized_via_brand_scoped_enum_processor(toml_text):
    assert "[[processors.enum]]" in toml_text
    assert f'brand = ["{BRAND}"]' in toml_text
    assert 'field = "device_fan_state"' in toml_text
    assert 'field = "device_psu_state"' in toml_text
    assert toml_text.count('"3" = 1') >= 2, "both fan and psu must remap 3 -> 1"


@pytest.mark.unit
def test_fan_psu_policy_thresholds_use_gt_one(policy):
    by_metric = {t["metric_name"]: t for t in policy["templates"]}
    for name in ("device_fan_state", "device_psu_state"):
        assert name in by_metric, f"policy missing {name}"
        methods = {th["method"] for th in by_metric[name]["threshold"]}
        values = {th["value"] for th in by_metric[name]["threshold"]}
        assert methods == {">"} and values == {1}, f"{name} must alert on >1"


# --------------------------------------------------------------------------- #
# dimension <-> data agreement: temp has descr (toml emits it); fan/psu do not
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_temperature_has_descr_dimension_matching_toml(metrics, toml_text):
    temp = {m["name"]: m for m in metrics["metrics"]}["device_temperature_celsius"]
    assert {d["name"] for d in temp["dimensions"]} == {"descr"}
    # toml device_temperature table emits a descr tag
    assert 'name = "descr"' in toml_text


@pytest.mark.unit
def test_fan_psu_have_no_descr_dimension(metrics):
    """fan/psu tables carry no descr name column, so the metrics must not
    declare a descr dimension that the series never carries."""
    by_name = {m["name"]: m for m in metrics["metrics"]}
    for name in ("device_fan_state", "device_psu_state"):
        assert by_name[name]["dimensions"] == [], f"{name} must declare no descr dimension"


@pytest.mark.unit
def test_alert_names_reference_descr_only_where_it_exists(policy):
    by_metric = {t["metric_name"]: t for t in policy["templates"]}
    # temperature has descr -> may use it
    assert "${metric_descr}" in by_metric["device_temperature_celsius"]["alert_name"]
    # fan/psu have no descr -> must not use it
    for name in ("device_fan_state", "device_psu_state"):
        assert "${metric_descr}" not in by_metric[name]["alert_name"], f"{name} dangling descr"


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
# secrets never inlined as plaintext
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_passwords_use_template_vars_not_plaintext(toml_text):
    for field in ("auth_password", "priv_password"):
        assert f'{field} = "{{{{ {field} }}}}"' in toml_text, f"{field} must be templated"
