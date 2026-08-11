"""Contract tests for the Huawei USG firewall SNMP plugin.

Huawei Secospace USG (enterprise 2011, HUAWEI-ENTITY-EXTENT-MIB) exposes
per-entity health OIDs on USG6390 Info-Finder:

  - CPU  hwEntityCpuUsage      1.3.6.1.4.1.2011.5.25.31.1.1.1.1.5  (direct %)
  - mem  hwEntityMemUsage      1.3.6.1.4.1.2011.5.25.31.1.1.1.1.7  (direct %)
  - temp hwEntityTemperature   1.3.6.1.4.1.2011.5.25.31.1.1.1.1.11 (°C)
  - volt hwEntityVoltage       1.3.6.1.4.1.2011.5.25.31.1.1.1.1.13 (mV; query /1000 → V)

CPU/memory/temperature/voltage are multi-entity tables (descr tag from
entPhysicalName). metrics.json keeps per-entity series with dimensions=[descr].
Memory is usage % ONLY (no used/free bytes).

Absent on USG6390 Info-Finder (do not model):
  - hwEntityFanState / hwEntityFanSlot (only FanReg yes/no exists)
  - hwEntityPwrState (only TotalPwrNum/NomalPwrNum counts)
  - optical Rx/Tx (USG9500-only)

collect_type is snmp_huawei_usg (distinct from switch snmp_huawei).
"""
import json
from pathlib import Path

import pytest
import yaml

from apps.core.utils.loader import LanguageLoader

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
BRAND_DIR = PLUGINS / "snmp" / "firewall_huawei"
BASE_DIR = PLUGINS / "snmp" / "firewall_hillstone"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "huawei"
COLLECT_TYPE = "snmp_huawei_usg"
CONFIG_TYPE = "huawei_usg"
INSTANCE_TYPE = "firewall"
PLUGIN_NAME = "Firewall Huawei SNMP"
OBJECT_NAME = "Firewall"
PEN_ROOT = "1.3.6.1.4.1.2011"

SUPPORTED_SCALAR_UNITS = {
    "byteps", "bytes", "counts", "cps", "percent", "celsius", "s", "short",
    "none", "bitps", "volts",
}
ABSENT_METRICS = (
    "device_memory_used", "device_memory_free",
    "device_fan_state", "device_psu_state",
    "device_optical_rx_power", "device_optical_tx_power",
)
HEALTH_METRICS = (
    "device_cpu_usage", "device_memory_usage", "device_temperature_celsius",
    "device_voltage_volts",
)


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def metrics():
    return _read_json(BRAND_DIR / "metrics.json")


@pytest.fixture(scope="module")
def base_metrics():
    return _read_json(BASE_DIR / "metrics.json")


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
        lang: LanguageLoader("monitor", lang).translations
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
def test_collect_type_distinct_from_switch_huawei():
    assert COLLECT_TYPE != "snmp_huawei"


@pytest.mark.unit
def test_ui_is_pure_snmp_form(ui):
    assert not any(f["name"] == "brand" for f in ui["form_fields"])


@pytest.mark.unit
def test_shared_metrics_match_baseline_group_and_unit(metrics, base_metrics):
    base = {m["name"]: m for m in base_metrics["metrics"]}
    drift = []
    for m in metrics["metrics"]:
        b = base.get(m["name"])
        if b is None:
            continue
        if m["metric_group"] != b["metric_group"]:
            drift.append(f'{m["name"]}.group')
        if m["unit"] != b["unit"]:
            drift.append(f'{m["name"]}.unit')
    assert drift == [], f"shared-metric drift vs Firewall baseline: {drift}"


@pytest.mark.unit
def test_health_metrics_present(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    missing = [h for h in HEALTH_METRICS if h not in names]
    assert missing == [], f"Huawei USG health metrics missing: {missing}"


@pytest.mark.unit
def test_cpu_is_percent_multi_dim_descr(metrics):
    cpu = {m["name"]: m for m in metrics["metrics"]}["device_cpu_usage"]
    assert cpu["unit"] == "percent"
    assert cpu["metric_group"] == "Firewall"
    assert [d["name"] for d in cpu["dimensions"]] == ["descr"]
    q = cpu["query"].replace(" ", "")
    assert "avg(" not in q and "by(instance_id)" not in q
    assert "device_cpu_usage{instance_type='firewall'" in q


@pytest.mark.unit
def test_memory_usage_is_direct_percent_multi_dim(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    assert "device_memory_usage" in by
    mu = by["device_memory_usage"]
    assert mu["unit"] == "percent"
    assert [d["name"] for d in mu["dimensions"]] == ["descr"]
    q = mu["query"].replace(" ", "")
    assert "avg(" not in q and "by(instance_id)" not in q
    assert "device_memory_used" not in q and "device_memory_free" not in q


@pytest.mark.unit
def test_temperature_is_celsius_multi_dim_descr(metrics):
    temp = {m["name"]: m for m in metrics["metrics"]}["device_temperature_celsius"]
    assert temp["unit"] == "celsius"
    assert temp["metric_group"] == "Firewall"
    assert [d["name"] for d in temp["dimensions"]] == ["descr"]
    q = temp["query"].replace(" ", "")
    assert "max(" not in q and "by(instance_id)" not in q
    assert "device_temperature_celsius{instance_type='firewall'" in q


@pytest.mark.unit
def test_voltage_is_volts_from_mv_multi_dim(metrics, toml_text):
    volt = {m["name"]: m for m in metrics["metrics"]}["device_voltage_volts"]
    assert volt["unit"] == "volts"
    assert [d["name"] for d in volt["dimensions"]] == ["descr"]
    q = volt["query"].replace(" ", "")
    assert "/1000" in q
    assert "1.3.6.1.4.1.2011.5.25.31.1.1.1.1.13" in toml_text
    # FanState / PSU state OIDs must not be collected
    assert "1.3.6.1.4.1.2011.5.25.31.1.1.10.1.7" not in toml_text
    assert "device_fan" not in toml_text
    assert "device_psu" not in toml_text


@pytest.mark.unit
def test_absent_metrics_not_modelled(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    present = [a for a in ABSENT_METRICS if a in names]
    assert present == [], f"must not model on USG6300/6390 template: {present}"


@pytest.mark.unit
def test_no_enum_processor_block(toml_text):
    assert "[[processors.enum]]" not in toml_text


@pytest.mark.unit
def test_private_oids_under_pen_2011(toml_text):
    assert "1.3.6.1.4.1.2011.5.25.31.1.1.1.1.5" in toml_text
    assert "1.3.6.1.4.1.2011.5.25.31.1.1.1.1.7" in toml_text
    assert "1.3.6.1.4.1.2011.5.25.31.1.1.1.1.11" in toml_text
    assert PEN_ROOT in toml_text


@pytest.mark.unit
def test_toml_collects_entity_descr_tag_for_multi_dim(toml_text):
    assert "1.3.6.1.2.1.47.1.1.1.1.7" in toml_text
    assert 'name = "descr"' in toml_text
    assert "is_tag = true" in toml_text


@pytest.mark.unit
def test_toml_collects_64bit_ifhc_counters(toml_text):
    assert "1.3.6.1.2.1.31.1.1.1.6" in toml_text
    assert "1.3.6.1.2.1.31.1.1.1.10" in toml_text


@pytest.mark.unit
def test_policy_covers_cpu_mem_temp(policy):
    names = {t["metric_name"] for t in policy["templates"]}
    assert "device_cpu_usage" in names
    assert "device_memory_usage" in names
    assert "device_temperature_celsius" in names


@pytest.mark.unit
def test_plugin_i18n_keys_present():
    zh = yaml.safe_load((BRAND_DIR / "language" / "zh-Hans.yaml").read_text(encoding="utf-8"))
    en = yaml.safe_load((BRAND_DIR / "language" / "en.yaml").read_text(encoding="utf-8"))
    assert PLUGIN_NAME in zh
    assert PLUGIN_NAME in en
    assert zh[PLUGIN_NAME]["name"]
    assert en[PLUGIN_NAME]["name"]


@pytest.mark.unit
def test_frontend_collect_type_wired():
    text = (WEB_ROOT / "src/app/monitor/hooks/integration/objects/networkDevice/firewall.tsx").read_text(
        encoding="utf-8"
    )
    assert f"'{PLUGIN_NAME}': '{COLLECT_TYPE}'" in text


@pytest.mark.unit
def test_huawei_brand_icon_match_exists():
    text = (WEB_ROOT / "src/app/monitor/utils/common.tsx").read_text(encoding="utf-8")
    assert "/huawei/i" in text


@pytest.mark.unit
def test_metric_units_supported(metrics):
    bad = []
    for m in metrics["metrics"]:
        unit = m.get("unit") or ""
        if unit.startswith("["):
            continue
        if unit not in SUPPORTED_SCALAR_UNITS:
            bad.append(f'{m["name"]}={unit}')
    assert bad == [], f"unsupported units: {bad}"


@pytest.mark.unit
def test_languages_fixture_loads(languages):
    assert "zh-Hans" in languages and "en" in languages
