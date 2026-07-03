"""Contract tests for the Sugon storage SNMP plugin.

Sugon ParaStor arrays reuse the MacroSAN private tree (enterprise PEN 35904).
This profile exposes hardware health only (no controller CPU/memory gauge):

  - device_fan_state  : fanState (.35904.1.2.2.3.2.1.2), enum 1=normal/2=fault
  - device_psu_state  : powerState (.35904.1.2.2.7.2.1.2), enum 1=normal/2=fault
  - device_disk_state : diskState (.35904.1.2.2.5.2.1.6), enum 1=normal/2=fault

CPU/memory/temperature are N/A. The storage object is shared.
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
BRAND_DIR = PLUGINS / "snmp" / "storage_sugon"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "sugon"
COLLECT_TYPE = "snmp_sugon"
CONFIG_TYPE = "sugon"
INSTANCE_TYPE = "storage"
PLUGIN_NAME = "Storage Sugon SNMP"
OBJECT_NAME = "Storage"
PEN_ROOT = "1.3.6.1.4.1.35904"

SUPPORTED_SCALAR_UNITS = {
    "byteps", "bytes", "bitps", "counts", "cps", "percent", "celsius", "s", "short", "none",
}
HC_METRICS = ("interface_ifHCInOctets", "interface_ifHCOutOctets")
STATE_METRICS = ("device_fan_state", "device_psu_state", "device_disk_state")


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


@pytest.mark.unit
def test_uses_private_pen_35904(toml_text):
    assert PEN_ROOT in toml_text, "Sugon ParaStor reuses PEN 35904"


@pytest.mark.unit
@pytest.mark.parametrize("name", STATE_METRICS)
def test_state_metric_is_enum_normalized(metrics, name):
    by = {m["name"]: m for m in metrics["metrics"]}
    assert name in by
    m = by[name]
    assert m["metric_group"] == "Hardware Status"
    q = m["query"].replace(" ", "")
    assert q.startswith("max(") and "by(instance_id)" in q
    ids = {opt["id"] for opt in json.loads(m["unit"])}
    assert {1, 2}.issubset(ids), f"{name} must expose 正常(1)/异常(2)"


@pytest.mark.unit
def test_enum_processors_normalize_states_to_1_normal(toml_text):
    for measurement in ("device_fan", "device_psu", "device_disk"):
        assert f'namepass = ["{measurement}"]' in toml_text
    assert toml_text.count("default = 2") >= 3
    assert '"1" = 1' in toml_text


@pytest.mark.unit
def test_no_cpu_memory_temperature_modelled(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    for absent in ("device_cpu_usage", "device_memory_usage", "device_temperature_celsius"):
        assert absent not in names, \
            f"{absent}: Sugon ParaStor profile has no such gauge -> N/A"


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
def test_hc_metrics_carry_ifdescr_dimension(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    for name in HC_METRICS:
        dims = [d["name"] for d in by[name].get("dimensions", [])]
        assert dims == ["ifDescr"], f"{name} must carry the ifDescr dimension"


@pytest.mark.unit
def test_toml_collects_64bit_ifhc_counters(toml_text):
    assert "1.3.6.1.2.1.31.1.1.1.6" in toml_text
    assert "1.3.6.1.2.1.31.1.1.1.10" in toml_text
    assert "ifHCInOctets" in toml_text and "ifHCOutOctets" in toml_text


@pytest.mark.unit
def test_toml_collects_iftable_and_uptime(toml_text):
    assert "1.3.6.1.2.1.1.3.0" in toml_text
    assert "1.3.6.1.2.1.2.2" in toml_text


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


@pytest.mark.unit
def test_policy_templates_reference_existing_metrics(metrics, policy):
    known = {m["name"] for m in metrics["metrics"]}
    bad = [t["metric_name"] for t in policy["templates"] if t["metric_name"] not in known]
    assert bad == [], f"policy references unknown metrics: {bad}"


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
def test_frontend_collecttype_wired_to_storage_object():
    storage_tsx = (
        WEB_ROOT / "src" / "app" / "monitor" / "hooks" / "integration"
        / "objects" / "hardwareDevice" / "storage.tsx"
    )
    text = storage_tsx.read_text(encoding="utf-8")
    assert f"'{PLUGIN_NAME}': '{COLLECT_TYPE}'" in text


@pytest.mark.unit
def test_storage_dashboard_renders_health_panels():
    storage_tsx = (
        WEB_ROOT / "src" / "app" / "monitor" / "hooks" / "integration"
        / "objects" / "hardwareDevice" / "storage.tsx"
    )
    text = storage_tsx.read_text(encoding="utf-8")
    for panel in ("device_fan_state", "device_psu_state", "device_disk_state"):
        assert panel in text, f"storage dashboardDisplay missing {panel} panel"


@pytest.mark.unit
def test_brand_match_present_in_common():
    common = WEB_ROOT / "src" / "app" / "monitor" / "utils" / "common.tsx"
    assert BRAND in common.read_text(encoding="utf-8")


@pytest.mark.unit
def test_passwords_use_template_vars_not_plaintext(toml_text):
    for field in ("auth_password", "priv_password"):
        assert f'{field} = "{{{{ {field} }}}}"' in toml_text
