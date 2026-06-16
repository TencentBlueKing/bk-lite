"""Contract tests for the D-Link DES/DGS switch SNMP plugin.

Validates Telegraf/snmp_dlink/switch against the Cisco baseline and the
cross-vendor design decisions for the SNMP brand-plugin family.

D-Link (EQUIPMENT-MIB, enterprise 171) reports CPU and memory as utilization
percentages directly (swCPUUtilizationIn5min / swDevInfoTotalUtilizationOfMemory)
— the same shape as Huawei — so device_memory_usage is a raw single series and
the shared brand-adaptive dashboard hits its raw branch with zero config change.
Temperature/fan/psu tables expose no descr name column, so none of those metrics
declare a descr dimension and their alert templates carry no ${metric_descr}.
swFanStatus / swPowerStatus are non-binary (a 0=other state exists below
normal), so BOTH are normalized to the unified 1=normal convention via a
brand-scoped enum processor (psu working=3 -> 1, fan working=1 -> 1, everything
else -> 2) — a plain policy `>1` on the raw codes would miss the 0=other state.

OID correctness is intentionally NOT tested here (pending on-site SNMP walk).
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
DLINK_DIR = PLUGINS / "snmp_dlink" / "switch"
CISCO_DIR = PLUGINS / "snmp_cisco" / "switch"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"

BRAND = "dlink"
COLLECT_TYPE = "snmp_dlink"
CONFIG_TYPE = "dlink"
PLUGIN_NAME = "Switch D-Link SNMP"
OBJECT_NAME = "Switch"

SUPPORTED_SCALAR_UNITS = {
    "byteps", "bytes", "counts", "cps", "percent", "celsius", "s", "short", "none",
}
INTERFACE_METRICS = ("interface_ifHCInOctets", "interface_ifHCOutOctets")


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def metrics():
    return _read_json(DLINK_DIR / "metrics.json")


@pytest.fixture(scope="module")
def cisco_metrics():
    return _read_json(CISCO_DIR / "metrics.json")


@pytest.fixture(scope="module")
def policy():
    return _read_json(DLINK_DIR / "policy.json")


@pytest.fixture(scope="module")
def ui():
    return _read_json(DLINK_DIR / "UI.json")


@pytest.fixture(scope="module")
def toml_text():
    return (DLINK_DIR / "dlink.child.toml.j2").read_text(encoding="utf-8")


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
# device_* parity with the Cisco baseline
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
# memory: %-direct single series (Huawei shape)
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_memory_is_direct_percent_raw_series(metrics):
    by_name = {m["name"]: m for m in metrics["metrics"]}
    usage = by_name["device_memory_usage"]
    assert usage["unit"] == "percent"
    assert usage["query"] == "device_memory_usage{instance_type='switch', __$labels__}"
    for absent in ("device_memory_used", "device_memory_free", "device_memory_total"):
        assert absent not in by_name, f"{absent} must not exist on a %-direct vendor"


# --------------------------------------------------------------------------- #
# fan/psu normalization to 1=normal (both; non-binary status has a 0=other)
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_fan_and_psu_normalized_via_brand_scoped_enum_processor(toml_text):
    assert "[[processors.enum]]" in toml_text
    assert f'brand = ["{BRAND}"]' in toml_text
    assert 'field = "device_fan_state"' in toml_text
    assert 'field = "device_psu_state"' in toml_text
    # psu working=3 -> 1, fan working=1 -> 1; default 2 maps every other code (incl 0=other)
    assert '"3" = 1' in toml_text and '"1" = 1' in toml_text
    assert toml_text.count("default = 2") >= 2


@pytest.mark.unit
def test_fan_psu_policy_thresholds_use_gt_one(policy):
    by_metric = {t["metric_name"]: t for t in policy["templates"]}
    for name in ("device_fan_state", "device_psu_state"):
        assert name in by_metric, f"policy missing {name}"
        methods = {th["method"] for th in by_metric[name]["threshold"]}
        values = {th["value"] for th in by_metric[name]["threshold"]}
        assert methods == {">"} and values == {1}, f"{name} must alert on >1"


# --------------------------------------------------------------------------- #
# no descr anywhere (temp/fan/psu tables have no descr name column)
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_health_metrics_have_no_descr_dimension(metrics):
    by_name = {m["name"]: m for m in metrics["metrics"]}
    for name in ("device_temperature_celsius", "device_fan_state", "device_psu_state"):
        assert by_name[name]["dimensions"] == [], f"{name} must declare no descr dimension"


@pytest.mark.unit
def test_alert_names_have_no_dangling_descr(policy):
    by_metric = {t["metric_name"]: t for t in policy["templates"]}
    for name in ("device_temperature_celsius", "device_fan_state", "device_psu_state"):
        assert "${metric_descr}" not in by_metric[name]["alert_name"], f"{name} dangling descr"


# --------------------------------------------------------------------------- #
# every switch vendor exposes the 64-bit ifHC interface traffic metrics
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
