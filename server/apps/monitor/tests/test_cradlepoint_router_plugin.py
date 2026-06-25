"""Contract tests for the Cradlepoint router SNMP plugin.

Cradlepoint NetCloud / COR / E-series / IBR-series cellular (4G/5G) routers
(IANA PEN 20992). Private scalar OIDs expose CPU utilization, memory
utilization (both direct percentages) and internal chassis temperature in
Celsius. Fan/power are not exposed as row-filter-free scalars -> N/A.

OID values are pending on-site SNMP walk; only the PEN root, the percent/celsius
units and the cross-file identity contract are asserted here.
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
BRAND_DIR = PLUGINS / "snmp" / "router_cradlepoint"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "cradlepoint"
COLLECT_TYPE = "snmp_cradlepoint"
CONFIG_TYPE = "cradlepoint"
INSTANCE_TYPE = "router"
PLUGIN_NAME = "Router Cradlepoint SNMP"
OBJECT_NAME = "Router"
PEN_ROOT = "1.3.6.1.4.1.20992"

SUPPORTED_SCALAR_UNITS = {
    "byteps", "bytes", "bitps", "counts", "cps", "percent", "celsius", "s", "short", "none",
}
HC_METRICS = ("interface_ifHCInOctets", "interface_ifHCOutOctets")


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
def test_uses_private_pen_20992(toml_text):
    assert PEN_ROOT in toml_text


@pytest.mark.unit
def test_cpu_and_memory_usage_percent(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    for name in ("device_cpu_usage", "device_memory_usage"):
        assert name in by
        assert by[name]["unit"] == "percent"
        q = by[name]["query"].replace(" ", "")
        assert q.startswith("avg(") and "by(instance_id)" in q


@pytest.mark.unit
def test_temperature_metric_is_celsius(metrics, toml_text):
    by = {m["name"]: m for m in metrics["metrics"]}
    assert "device_temperature_celsius" in by
    assert by["device_temperature_celsius"]["unit"] == "celsius"
    assert 'name = "celsius"' in toml_text


@pytest.mark.unit
def test_no_used_free_without_usage(metrics):
    # Cradlepoint reports memory only as a direct percentage -> no used/free split.
    names = {m["name"] for m in metrics["metrics"]}
    assert "device_memory_used" not in names
    assert "device_memory_free" not in names
    assert "device_fan_state" not in names
    assert "device_psu_state" not in names


@pytest.mark.unit
def test_hc_metrics_present_64bit(metrics, toml_text):
    by = {m["name"]: m for m in metrics["metrics"]}
    for name in HC_METRICS:
        assert name in by
        assert by[name]["unit"] == "byteps"
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
def test_dimensions_well_formed(metrics):
    bad = [
        m["name"]
        for m in metrics["metrics"]
        for d in m.get("dimensions", [])
        if not d.get("name") or not d.get("description")
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
def test_frontend_collecttype_wired_to_router_object():
    router_tsx = (
        WEB_ROOT / "src" / "app" / "monitor" / "hooks" / "integration"
        / "objects" / "networkDevice" / "router.tsx"
    )
    text = router_tsx.read_text(encoding="utf-8")
    assert f"'{PLUGIN_NAME}': '{COLLECT_TYPE}'" in text


@pytest.mark.unit
def test_brand_label_present_in_common():
    common = WEB_ROOT / "src" / "app" / "monitor" / "utils" / "common.tsx"
    assert BRAND in common.read_text(encoding="utf-8")


@pytest.mark.unit
def test_passwords_use_template_vars_not_plaintext(toml_text):
    for field in ("auth_password", "priv_password"):
        assert f'{field} = "{{{{ {field} }}}}"' in toml_text
