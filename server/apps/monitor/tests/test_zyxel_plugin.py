"""Contract tests for the Zyxel switch SNMP plugin.

Validates Telegraf/snmp_zyxel/switch against the Cisco baseline and the
cross-vendor design decisions for the SNMP brand-plugin family.

The Zyxel GS-series MIB (ZYXEL private, enterprise 890) exposes a CPU
utilization scalar and a temperature sensor, but no memory-utilization OID, no
fan state and no PSU state on this switch line — so this is a CPU + temperature
profile with no memory metric at all. There are no memory/fan/psu metrics, no
enum processor, the policy carries only CPU and temperature templates, and the
supplementary_indicators must not reference the absent device_memory_usage.
Like every switch vendor it still exposes the 64-bit ifHC interface metrics.

OID correctness is intentionally NOT tested here (pending on-site SNMP walk).
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
ZYXEL_DIR = PLUGINS / "snmp" / "switch_zyxel"
CISCO_DIR = PLUGINS / "snmp" / "switch_cisco"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"

BRAND = "zyxel"
COLLECT_TYPE = "snmp_zyxel"
CONFIG_TYPE = "zyxel"
PLUGIN_NAME = "Switch Zyxel SNMP"
OBJECT_NAME = "Switch"

SUPPORTED_SCALAR_UNITS = {
    "byteps", "bytes", "counts", "cps", "percent", "celsius", "s", "short", "none",
}
INTERFACE_METRICS = ("interface_ifHCInOctets", "interface_ifHCOutOctets")
ABSENT_METRICS = (
    "device_memory_usage", "device_memory_used", "device_memory_free",
    "device_memory_total", "device_fan_state", "device_psu_state",
)


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def metrics():
    return _read_json(ZYXEL_DIR / "metrics.json")


@pytest.fixture(scope="module")
def cisco_metrics():
    return _read_json(CISCO_DIR / "metrics.json")


@pytest.fixture(scope="module")
def policy():
    return _read_json(ZYXEL_DIR / "policy.json")


@pytest.fixture(scope="module")
def ui():
    return _read_json(ZYXEL_DIR / "UI.json")


@pytest.fixture(scope="module")
def toml_text():
    return (ZYXEL_DIR / "zyxel.child.toml.j2").read_text(encoding="utf-8")


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
# reduced profile: CPU + temperature + interface traffic, no memory/fan/psu
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_reduced_profile_absent_metrics(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    present = [a for a in ABSENT_METRICS if a in names]
    assert present == [], f"unexpected metrics for a CPU+temp-only vendor: {present}"


@pytest.mark.unit
def test_no_enum_processor_in_toml(toml_text):
    assert "[[processors.enum]]" not in toml_text


@pytest.mark.unit
def test_policy_only_cpu_and_temperature(policy):
    names = {t["metric_name"] for t in policy["templates"]}
    assert names == {"device_cpu_usage", "device_temperature_celsius"}


@pytest.mark.unit
def test_supplementary_indicators_have_no_dangling_refs(metrics):
    """A memory-less vendor must not advertise device_memory_usage as a
    supplementary indicator (it has no such metric)."""
    names = {m["name"] for m in metrics["metrics"]}
    dangling = [s for s in metrics.get("supplementary_indicators", []) if s not in names]
    assert dangling == [], f"supplementary_indicators reference absent metrics: {dangling}"


# --------------------------------------------------------------------------- #
# device_* / interface parity with the Cisco baseline
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
def test_cpu_query_byte_identical_to_cisco(metrics, cisco_metrics):
    ext = {m["name"]: m for m in metrics["metrics"]}["device_cpu_usage"]
    cis = {m["name"]: m for m in cisco_metrics["metrics"]}["device_cpu_usage"]
    assert ext["query"] == cis["query"]


@pytest.mark.unit
def test_temperature_has_no_descr_dimension(metrics):
    temp = {m["name"]: m for m in metrics["metrics"]}["device_temperature_celsius"]
    assert temp["dimensions"] == []


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
