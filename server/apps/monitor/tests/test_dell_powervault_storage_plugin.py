"""Contract tests for the Dell PowerVault storage SNMP plugin.

The local DellStorage profile targets Dell / EqualLogic PEN 12740 and exposes:

  - device_cpu_usage: Cisco cpmCPUTotal5min, direct percent
  - device_temperature_celsius: controller processor and chipset temperatures
  - device_disk_state: eqlDiskStatus, online(1) normalized to healthy
  - device_raid_state: eqliscsiVolumeAdminStatus, online(1) normalized to healthy

Capacity, RPM, CPU frequency, and physical RAM are inventory/specification
values, not shared storage health signals, so they are intentionally not modeled.
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
BRAND_DIR = PLUGINS / "snmp" / "storage_dellpowervault"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "dellpowervault"
COLLECT_TYPE = "snmp_dellpowervault"
CONFIG_TYPE = "dellpowervault"
INSTANCE_TYPE = "storage"
PLUGIN_NAME = "Storage Dell PowerVault SNMP"
OBJECT_NAME = "Storage"
PEN_ROOT = "1.3.6.1.4.1.12740"
CPU_OID = "1.3.6.1.4.1.9.9.109.1.1.1.1.5"
TEMP_OIDS = (
    "1.3.6.1.4.1.12740.4.1.1.1.7",
    "1.3.6.1.4.1.12740.4.1.1.1.8",
)
HC_METRICS = ("interface_ifHCInOctets", "interface_ifHCOutOctets")
STATE_METRICS = ("device_disk_state", "device_raid_state")


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
def test_collect_type_consistent_across_files(metrics, policy, ui, toml_text):
    assert metrics["collect_type"] == COLLECT_TYPE
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
def test_uses_dell_equal_logic_private_pen(toml_text):
    assert PEN_ROOT in toml_text


@pytest.mark.unit
def test_cpu_is_direct_percent(metrics, toml_text):
    by = {m["name"]: m for m in metrics["metrics"]}
    cpu = by["device_cpu_usage"]
    assert cpu["unit"] == "percent"
    assert cpu["metric_group"] == "CPU"
    assert cpu["query"].replace(" ", "").startswith("max(")
    assert CPU_OID in toml_text


@pytest.mark.unit
def test_temperature_is_celsius_no_scaling(metrics, toml_text):
    by = {m["name"]: m for m in metrics["metrics"]}
    temp = by["device_temperature_celsius"]
    assert temp["unit"] == "celsius"
    assert temp["metric_group"] == "Temperature"
    assert temp["query"].replace(" ", "").startswith("max(")
    for oid in TEMP_OIDS:
        assert oid in toml_text


@pytest.mark.unit
@pytest.mark.parametrize("name", STATE_METRICS)
def test_state_metric_is_enum_normalized(metrics, name):
    by = {m["name"]: m for m in metrics["metrics"]}
    metric = by[name]
    assert metric["metric_group"] == "Hardware Status"
    assert metric["query"].replace(" ", "").startswith("max(")
    ids = {opt["id"] for opt in json.loads(metric["unit"])}
    assert {1, 2}.issubset(ids)


@pytest.mark.unit
def test_enum_processors_normalize_online_to_1_normal(toml_text):
    for measurement in ("device_disk", "device_raid"):
        assert f'namepass = ["{measurement}"]' in toml_text
    assert toml_text.count("default = 2") >= 2
    assert toml_text.count('"1" = 1') >= 2


@pytest.mark.unit
def test_no_memory_fan_psu_modelled(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    for absent in ("device_memory_usage", "device_fan_state", "device_psu_state"):
        assert absent not in names


@pytest.mark.unit
def test_static_capacity_and_inventory_metrics_not_modelled(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    blocked = {
        "eqlDiskSize",
        "eqlDiskRPM",
        "eqlControllerCPUfreq",
        "eqlControllerPhysRam",
        "eqliscsiVolumeSize",
    }
    assert not names.intersection(blocked)


@pytest.mark.unit
def test_hc_metrics_declared_as_byteps_rate_with_ifdescr(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    for name in HC_METRICS:
        metric = by[name]
        assert metric["unit"] == "byteps"
        assert metric["metric_group"] == "Traffic"
        assert metric["query"].startswith("rate(")
        assert [d["name"] for d in metric.get("dimensions", [])] == ["ifDescr"]


@pytest.mark.unit
def test_toml_collects_ifxtable_and_64bit_hc(toml_text):
    assert 'oid = "1.3.6.1.2.1.2.2"' in toml_text
    assert 'oid = "1.3.6.1.2.1.2.2.1.2"' in toml_text
    assert "1.3.6.1.2.1.31.1.1.1.6" in toml_text
    assert "1.3.6.1.2.1.31.1.1.1.10" in toml_text
    assert "ifHCInOctets" in toml_text and "ifHCOutOctets" in toml_text


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
    assert f"'{PLUGIN_NAME}': '{COLLECT_TYPE}'" in storage_tsx.read_text(encoding="utf-8")


@pytest.mark.unit
def test_brand_match_present_in_common():
    common = WEB_ROOT / "src" / "app" / "monitor" / "utils" / "common.tsx"
    text = common.read_text(encoding="utf-8").lower()
    assert "powervault" in text or "equallogic" in text


@pytest.mark.unit
def test_passwords_use_template_vars_not_plaintext(toml_text):
    for field in ("auth_password", "priv_password"):
        assert f'{field} = "{{{{ {field} }}}}"' in toml_text
