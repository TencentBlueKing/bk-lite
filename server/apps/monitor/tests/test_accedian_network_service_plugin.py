"""Contract tests for the Accedian network-service SNMP plugin.

Accedian metro-Ethernet performance-assurance nodes (IANA PEN 22420,
ACD-DESC-MIB). The device-description MIB exposes a private scalar OID for
chassis CPU utilization (acdDescCpuUsageCurrent, Gauge32 0..100, direct %).
There is no memory-usage scalar in the MIB, and the only temperature reading
is the per-SFP diagnostics table (ACD-SFP-MIB acdSfpDiagTemp, row-indexed)
that the SNMP input cannot row-filter -> memory/temperature/fan/power are N/A.
Traffic uses 64-bit IF-MIB HC counters.

OID values for the private CPU OID are pending on-site SNMP walk; the PEN root,
the percent units, the 64-bit HC contract and cross-file identity are asserted.
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
BRAND_DIR = PLUGINS / "snmp" / "network_service_accedian"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "accedian"
COLLECT_TYPE = "snmp_accedian"
CONFIG_TYPE = "accedian"
INSTANCE_TYPE = "network_service"
PLUGIN_NAME = "NetworkService Accedian SNMP"
OBJECT_NAME = "NetworkService"
PEN_ROOT = "1.3.6.1.4.1.22420"
CPU_OID = "1.3.6.1.4.1.22420.1.1.20.0"

SUPPORTED_SCALAR_UNITS = {
    "byteps", "bytes", "bitps", "counts", "cps", "percent", "celsius", "s", "short", "none",
}
HC_METRICS = ("interface_ifHCInOctets", "interface_ifHCOutOctets")
TOTAL_METRICS = ("device_total_incoming_traffic", "device_total_outgoing_traffic")


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
def test_uses_private_pen_22420(toml_text):
    assert PEN_ROOT in toml_text
    assert CPU_OID in toml_text


@pytest.mark.unit
def test_cpu_usage_percent(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    assert "device_cpu_usage" in by
    assert by["device_cpu_usage"]["unit"] == "percent"
    q = by["device_cpu_usage"]["query"].replace(" ", "")
    assert q.startswith("avg(") and "by(instance_id)" in q


@pytest.mark.unit
def test_no_memory_temperature_or_env_sensors(metrics):
    # ACD-DESC-MIB has no memory scalar; temperature is per-SFP table only -> all N/A.
    names = {m["name"] for m in metrics["metrics"]}
    for absent in ("device_memory_usage", "device_memory_used", "device_memory_free",
                   "device_temperature_celsius", "device_fan_state", "device_psu_state"):
        assert absent not in names, f"{absent} not exposed as a scalar by ACD-DESC-MIB -> N/A"


@pytest.mark.unit
def test_toml_has_no_enum_block(toml_text):
    # No fan/psu normalization needed for a CPU-only baseline.
    assert "processors.enum" not in toml_text


@pytest.mark.unit
def test_uptime_metric_present(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    assert "snmp_uptime" in by
    assert by["snmp_uptime"]["unit"] == "s"


@pytest.mark.unit
def test_hc_metrics_present_64bit(metrics, toml_text):
    by = {m["name"]: m for m in metrics["metrics"]}
    for name in HC_METRICS:
        assert name in by
        assert by[name]["unit"] == "byteps"
        assert by[name]["query"].startswith("rate(")
    assert "1.3.6.1.2.1.31.1.1.1.6" in toml_text
    assert "1.3.6.1.2.1.31.1.1.1.10" in toml_text
    # must NOT fall back to 32-bit octet counters
    assert "1.3.6.1.2.1.2.2.1.10" not in toml_text


@pytest.mark.unit
def test_device_total_rollups_use_hc(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    for name in TOTAL_METRICS:
        assert name in by
        q = by[name]["query"].replace(" ", "")
        assert q.startswith("sum(rate(") and "by(instance_id)" in q
        assert "ifHC" in q, "device_total_* must roll up the 64-bit HC counters"


@pytest.mark.unit
def test_toml_collects_uptime(toml_text):
    assert "1.3.6.1.2.1.1.3.0" in toml_text


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
    bad = [t["metric_name"] for t in policy["templates"] if t["metric_name"] not in known]
    assert bad == []


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
def test_frontend_collecttype_wired_to_network_service_object():
    ns_tsx = (
        WEB_ROOT / "src" / "app" / "monitor" / "hooks" / "integration"
        / "objects" / "networkDevice" / "networkService.tsx"
    )
    text = ns_tsx.read_text(encoding="utf-8")
    assert f"'{PLUGIN_NAME}': '{COLLECT_TYPE}'" in text


@pytest.mark.unit
def test_brand_label_present_in_common():
    common = WEB_ROOT / "src" / "app" / "monitor" / "utils" / "common.tsx"
    assert BRAND in common.read_text(encoding="utf-8")


@pytest.mark.unit
def test_passwords_use_template_vars_not_plaintext(toml_text):
    for field in ("auth_password", "priv_password"):
        assert f'{field} = "{{{{ {field} }}}}"' in toml_text
