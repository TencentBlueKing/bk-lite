"""Contract tests for the Aerohive (Extreme Networks) wireless SNMP plugin.

Aerohive HiveAP / HiveOS devices (enterprise PEN 26928) expose pollable
platform health scalars in AH-SYSTEM-MIB: ahCpuUtilization (.26928.1.2.3,
INTEGER 0..100 direct %), ahMemUtilization (.26928.1.2.4, INTEGER 0..100
direct %), and ahEnvirmentTemp (.26928.1.2.10, INTEGER degrees Celsius read
directly with no /10 scaling; only sensor-equipped chassis return a real value,
fanless APs return 0). The fan object ahEnvirmentFan is an RPM speed reading
rather than a normalized up/down state, and there is no power-supply object, so
fan/psu state are N/A. The plugin therefore carries CPU/memory/temperature
health on top of the 64-bit IF-MIB HC interface baseline.
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
BRAND_DIR = PLUGINS / "snmp" / "wireless_aerohive"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "aerohive"
COLLECT_TYPE = "snmp_aerohive"
CONFIG_TYPE = "aerohive"
INSTANCE_TYPE = "wireless"
PLUGIN_NAME = "Wireless Aerohive SNMP"
OBJECT_NAME = "Wireless"

# AH-SYSTEM-MIB scalar OIDs (PEN 26928)
OID_CPU = "1.3.6.1.4.1.26928.1.2.3.0"
OID_MEM = "1.3.6.1.4.1.26928.1.2.4.0"
OID_TEMP = "1.3.6.1.4.1.26928.1.2.10.0"

SUPPORTED_SCALAR_UNITS = {
    "byteps", "bytes", "bitps", "counts", "cps", "percent", "celsius", "s", "short", "none",
}
HC_METRICS = ("interface_ifHCInOctets", "interface_ifHCOutOctets")
TOTAL_METRICS = ("device_total_incoming_traffic", "device_total_outgoing_traffic")
HEALTH_METRICS = ("device_cpu_usage", "device_memory_usage", "device_temperature_celsius")


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
def test_uptime_metric_present(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    assert "snmp_uptime" in by
    assert by["snmp_uptime"]["unit"] == "s"


@pytest.mark.unit
def test_hc_metrics_declared_as_byteps_rate(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    for name in HC_METRICS:
        assert name in by
        m = by[name]
        assert m["unit"] == "byteps"
        assert m["metric_group"] == "Traffic"
        assert m["query"].startswith("rate(")


@pytest.mark.unit
def test_device_total_rollups_present(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    for name in TOTAL_METRICS:
        assert name in by
        q = by[name]["query"].replace(" ", "")
        assert q.startswith("sum(rate(") and "by(instance_id)" in q


@pytest.mark.unit
def test_cpu_and_memory_are_direct_percent(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    for name in ("device_cpu_usage", "device_memory_usage"):
        assert name in by
        assert by[name]["unit"] == "percent"
    # direct % reading -> no used/free/total byte pool modeled
    names = {m["name"] for m in metrics["metrics"]}
    for absent in ("device_memory_used", "device_memory_free", "device_memory_total"):
        assert absent not in names


@pytest.mark.unit
def test_temperature_present_in_celsius(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    assert "device_temperature_celsius" in by
    assert by["device_temperature_celsius"]["unit"] == "celsius"


@pytest.mark.unit
def test_fan_and_psu_are_na(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    # ahEnvirmentFan is an RPM speed reading, not a normalized state; no PSU object
    for absent in ("device_fan_state", "device_psu_state"):
        assert absent not in names


@pytest.mark.unit
def test_toml_collects_health_oids(toml_text):
    assert OID_CPU in toml_text
    assert OID_MEM in toml_text
    assert OID_TEMP in toml_text


@pytest.mark.unit
def test_temperature_oid_has_no_scaling(toml_text, metrics):
    # ahEnvirmentTemp is degrees Celsius read directly -> no /10 in query or toml
    by = {m["name"]: m for m in metrics["metrics"]}
    assert "/10" not in by["device_temperature_celsius"]["query"]
    assert "/10" not in toml_text


@pytest.mark.unit
def test_no_fan_rpm_field_collected_as_state(toml_text):
    # ahEnvirmentFan OID (.26928.1.2.11) must NOT be wired as a state metric
    assert "1.3.6.1.4.1.26928.1.2.11" not in toml_text


@pytest.mark.unit
def test_toml_collects_64bit_ifhc_counters(toml_text):
    assert "1.3.6.1.2.1.31.1.1.1.6" in toml_text
    assert "1.3.6.1.2.1.31.1.1.1.10" in toml_text


@pytest.mark.unit
def test_toml_collects_iftable_and_uptime(toml_text):
    assert "1.3.6.1.2.1.1.3.0" in toml_text
    assert "1.3.6.1.2.1.2.2" in toml_text


@pytest.mark.unit
def test_supplementary_indicators_have_no_dangling_refs(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    dangling = [s for s in metrics.get("supplementary_indicators", []) if s not in names]
    assert dangling == []


@pytest.mark.unit
def test_all_scalar_metric_units_supported(metrics):
    bad = [
        f'{m["name"]}:{m["unit"]}'
        for m in metrics["metrics"]
        if m["data_type"] != "Enum" and m["unit"] not in SUPPORTED_SCALAR_UNITS
    ]
    assert bad == []


@pytest.mark.unit
def test_policy_templates_reference_existing_metrics(metrics, policy):
    known = {m["name"] for m in metrics["metrics"]}
    bad = [t["metric_name"] for t in policy.get("templates", []) if t["metric_name"] not in known]
    assert bad == []


@pytest.mark.unit
def test_policy_covers_health_metrics(policy):
    covered = {t["metric_name"] for t in policy.get("templates", [])}
    for name in HEALTH_METRICS:
        assert name in covered, f"{name} should have a policy threshold"


@pytest.mark.unit
def test_plugin_has_bilingual_name_and_desc(languages):
    for lang, data in languages.items():
        entry = (data.get("monitor_object_plugin") or {}).get(PLUGIN_NAME) or {}
        assert entry.get("name"), f"{lang}: plugin name missing"
        assert entry.get("desc"), f"{lang}: plugin desc missing"


@pytest.mark.unit
def test_en_desc_has_no_halfwidth_colon_space(languages):
    en = (languages["en"].get("monitor_object_plugin") or {}).get(PLUGIN_NAME) or {}
    assert ": " not in en.get("desc", "")


@pytest.mark.unit
def test_wireless_metric_translations_present(languages):
    for lang, data in languages.items():
        block = (data.get("monitor_object_metric") or {}).get(OBJECT_NAME) or {}
        for name in HEALTH_METRICS:
            assert name in block, f"{lang}: Wireless metric translation missing for {name}"


@pytest.mark.unit
def test_wireless_metric_groups_translated(languages):
    for lang, data in languages.items():
        groups = (data.get("monitor_object_metric_group") or {}).get(OBJECT_NAME) or {}
        for grp in ("Wireless", "Temperature"):
            assert grp in groups, f"{lang}: Wireless metric_group missing {grp}"


@pytest.mark.unit
def test_frontend_collecttype_wired_to_wireless_object():
    wireless_tsx = (
        WEB_ROOT / "src" / "app" / "monitor" / "hooks" / "integration"
        / "objects" / "networkDevice" / "wireless.tsx"
    )
    text = wireless_tsx.read_text(encoding="utf-8")
    assert f"'{PLUGIN_NAME}': '{COLLECT_TYPE}'" in text


@pytest.mark.unit
def test_brand_match_present_in_common():
    common = WEB_ROOT / "src" / "app" / "monitor" / "utils" / "common.tsx"
    assert BRAND in common.read_text(encoding="utf-8")


@pytest.mark.unit
def test_passwords_use_template_vars_not_plaintext(toml_text):
    for field in ("auth_password", "priv_password"):
        assert f'{field} = "{{{{ {field} }}}}"' in toml_text
