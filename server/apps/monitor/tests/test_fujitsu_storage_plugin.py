"""Contract tests for the Fujitsu ETERNUS storage SNMP plugin.

Fujitsu ETERNUS arrays expose chassis temperature and RAID/volume status under
Fujitsu enterprise PEN 211 (fjdary-MIB). CPU, memory, fan, and power-supply state
are N/A in the local profile.
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
BRAND_DIR = PLUGINS / "snmp" / "storage_fujitsu"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "fujitsu"
COLLECT_TYPE = "snmp_fujitsu"
CONFIG_TYPE = "fujitsu"
INSTANCE_TYPE = "storage"
PLUGIN_NAME = "Storage Fujitsu SNMP"
OBJECT_NAME = "Storage"
PEN_ROOT = "1.3.6.1.4.1.211.1.21.1.100"
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
def test_collect_type_consistent_across_files(metrics, policy, ui, toml_text):
    assert metrics["collect_type"] == COLLECT_TYPE
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
def test_uses_fujitsu_private_pen(toml_text):
    assert PEN_ROOT in toml_text


@pytest.mark.unit
def test_temperature_is_celsius_no_scaling(metrics, toml_text):
    by = {m["name"]: m for m in metrics["metrics"]}
    temp = by["device_temperature_celsius"]
    assert temp["unit"] == "celsius"
    assert temp["metric_group"] == "Temperature"
    assert "1.3.6.1.4.1.211.1.21.1.100.13.3.2.1.5" in toml_text


@pytest.mark.unit
def test_raid_state_is_ok_2_normalized_to_1(metrics, toml_text):
    by = {m["name"]: m for m in metrics["metrics"]}
    raid = by["device_raid_state"]
    assert raid["metric_group"] == "Hardware Status"
    assert raid["query"].replace(" ", "").startswith("max(")
    ids = {opt["id"] for opt in json.loads(raid["unit"])}
    assert {1, 2}.issubset(ids)
    assert 'namepass = ["device_raid"]' in toml_text
    assert "default = 2" in toml_text
    assert '"2" = 1' in toml_text


@pytest.mark.unit
def test_no_cpu_memory_fan_psu_modelled(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    for absent in ("device_cpu_usage", "device_memory_usage", "device_fan_state", "device_psu_state"):
        assert absent not in names


@pytest.mark.unit
def test_hc_metrics_declared_as_byteps_rate_with_ifname(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    for name in HC_METRICS:
        metric = by[name]
        assert metric["unit"] == "byteps"
        assert metric["metric_group"] == "Traffic"
        assert metric["query"].startswith("rate(")
        assert [d["name"] for d in metric.get("dimensions", [])] == ["ifName"]


@pytest.mark.unit
def test_toml_collects_ifxtable_ifname_and_64bit_hc(toml_text):
    assert 'oid = "1.3.6.1.2.1.31.1.1"' in toml_text
    assert 'oid = "1.3.6.1.2.1.31.1.1.1.1"' in toml_text
    assert "ifName" in toml_text
    assert "1.3.6.1.2.1.31.1.1.1.6" in toml_text
    assert "1.3.6.1.2.1.31.1.1.1.10" in toml_text
    assert "1.3.6.1.2.1.2.2" not in toml_text
    assert "ifDescr" not in toml_text


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
    assert BRAND in common.read_text(encoding="utf-8")
