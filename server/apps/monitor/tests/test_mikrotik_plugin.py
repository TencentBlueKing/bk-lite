"""Contract tests for the MikroTik (RouterOS) switch SNMP plugin.

Validates Telegraf/snmp_mikrotik/switch against the Cisco baseline and the
cross-vendor design decisions for the SNMP brand-plugin family.

MikroTik is a REDUCED health profile: it exposes per-core CPU
(HOST-RESOURCES hrProcessorLoad), system memory as a used/total byte pool
(hrStorage at the main-memory index) and board temperature
(MIKROTIK-MIB mtxrHlTemperature). Fan is raw RPM (not a state) and PSU state is
not standardized, so neither is collected (N/A) — there are no fan/psu metrics,
no enum processor, and the policy has no fan/psu templates. Memory utilization
is computed used/total (dashboard branch-3). Like every switch vendor it must
still expose the 64-bit ifHC interface traffic metrics.

OID correctness is intentionally NOT tested here (pending on-site SNMP walk).
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
MIKROTIK_DIR = PLUGINS / "snmp_mikrotik" / "switch"
CISCO_DIR = PLUGINS / "snmp_cisco" / "switch"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"

BRAND = "mikrotik"
COLLECT_TYPE = "snmp_mikrotik"
CONFIG_TYPE = "mikrotik"
PLUGIN_NAME = "Switch MikroTik SNMP"
OBJECT_NAME = "Switch"

SUPPORTED_SCALAR_UNITS = {
    "byteps", "bytes", "counts", "cps", "percent", "celsius", "s", "short", "none",
}
INTERFACE_METRICS = ("interface_ifHCInOctets", "interface_ifHCOutOctets")


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def metrics():
    return _read_json(MIKROTIK_DIR / "metrics.json")


@pytest.fixture(scope="module")
def cisco_metrics():
    return _read_json(CISCO_DIR / "metrics.json")


@pytest.fixture(scope="module")
def policy():
    return _read_json(MIKROTIK_DIR / "policy.json")


@pytest.fixture(scope="module")
def ui():
    return _read_json(MIKROTIK_DIR / "UI.json")


@pytest.fixture(scope="module")
def toml_text():
    return (MIKROTIK_DIR / "mikrotik.child.toml.j2").read_text(encoding="utf-8")


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
# reduced health profile: no fan/psu anywhere
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_no_fan_psu_metrics(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    assert "device_fan_state" not in names
    assert "device_psu_state" not in names


@pytest.mark.unit
def test_no_enum_processor_in_toml(toml_text):
    """No fan/psu states to normalize, so there must be no enum processor."""
    assert "[[processors.enum]]" not in toml_text


@pytest.mark.unit
def test_policy_has_no_fan_psu_templates(policy):
    names = {t["metric_name"] for t in policy["templates"]}
    assert "device_fan_state" not in names
    assert "device_psu_state" not in names
    # exactly the three health templates
    assert names == {"device_cpu_usage", "device_memory_usage", "device_temperature_celsius"}


# --------------------------------------------------------------------------- #
# device_* parity with Cisco for the metrics that ARE present
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


# --------------------------------------------------------------------------- #
# byte-pool memory: used/total (NOT used/free), ordered before computed usage
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_memory_used_total_ordered_before_usage(metrics):
    order = [m["name"] for m in metrics["metrics"]]
    idx = {n: i for i, n in enumerate(order)}
    for raw in ("device_memory_used", "device_memory_total"):
        assert raw in idx, f"{raw} missing"
        assert idx[raw] < idx["device_memory_usage"], f"{raw} must precede memory_usage"
    # MikroTik has no free series in this model
    assert "device_memory_free" not in idx


@pytest.mark.unit
def test_memory_usage_computed_from_used_and_total(metrics):
    usage = {m["name"]: m for m in metrics["metrics"]}["device_memory_usage"]
    assert usage["unit"] == "percent"
    assert "device_memory_used" in usage["query"]
    assert "device_memory_total" in usage["query"]


# --------------------------------------------------------------------------- #
# scalar temperature: no descr dimension, no dangling alert descr
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_temperature_has_no_descr_dimension(metrics):
    temp = {m["name"]: m for m in metrics["metrics"]}["device_temperature_celsius"]
    assert temp["dimensions"] == []


@pytest.mark.unit
def test_temperature_alert_name_has_no_dangling_descr(policy):
    temp = [t for t in policy["templates"] if t["metric_name"] == "device_temperature_celsius"]
    assert temp and "${metric_descr}" not in temp[0]["alert_name"]


# --------------------------------------------------------------------------- #
# every switch vendor exposes the 64-bit ifHC interface traffic metrics
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_interface_hc_metrics_present_and_match_cisco(metrics, cisco_metrics):
    ext = {m["name"]: m for m in metrics["metrics"]}
    cis = {m["name"]: m for m in cisco_metrics["metrics"]}
    for name in INTERFACE_METRICS:
        assert name in ext, f"{name} must be declared (toml collects it)"
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
# i18n completeness (zh-Hans + en) — includes the interface metrics + Traffic
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
