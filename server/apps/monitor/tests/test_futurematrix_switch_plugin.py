"""Contract tests for the FutureMatrix switch SNMP plugin.

FutureMatrix S1730S (enterprise 56813, FMEntity*) mirrors Huawei switch metrics
with PEN 2011→56813 OID swap. Multi-dimensional health metrics use descr tags.
Optical Rx/Tx is stored as raw µW; metrics query converts via 10*log10(µW/1000).
PSU omitted to align with Switch Huawei SNMP (even though FMEntityPwrState exists).
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
BRAND_DIR = PLUGINS / "snmp" / "switch_futurematrix"
HUAWEI_DIR = PLUGINS / "snmp" / "switch_huawei"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

COLLECT_TYPE = "snmp_futurematrix"
CONFIG_TYPE = "futurematrix"
PLUGIN_NAME = "Switch FutureMatrix SNMP"
PEN = "1.3.6.1.4.1.56813"
HUAWEI_PEN = "1.3.6.1.4.1.2011"

HEALTH = (
    "device_cpu_usage",
    "device_memory_usage",
    "device_temperature_celsius",
    "device_fan_state",
    "device_optical_rx_power",
    "device_optical_tx_power",
)
MULTI_DIM = (
    "device_cpu_usage",
    "device_memory_usage",
    "device_temperature_celsius",
    "device_fan_state",
    "device_optical_rx_power",
    "device_optical_tx_power",
)


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def metrics():
    return _read_json(BRAND_DIR / "metrics.json")


@pytest.fixture(scope="module")
def huawei_metrics():
    return _read_json(HUAWEI_DIR / "metrics.json")


@pytest.fixture(scope="module")
def ui():
    return _read_json(BRAND_DIR / "UI.json")


@pytest.fixture(scope="module")
def policy():
    return _read_json(BRAND_DIR / "policy.json")


@pytest.fixture(scope="module")
def toml_text():
    return (BRAND_DIR / f"{CONFIG_TYPE}.child.toml.j2").read_text(encoding="utf-8")


@pytest.mark.unit
def test_identity(metrics, ui, policy, toml_text):
    assert metrics["collect_type"] == COLLECT_TYPE
    assert metrics["plugin"] == PLUGIN_NAME
    assert policy["plugin"] == PLUGIN_NAME
    assert ui["collect_type"] == COLLECT_TYPE
    assert ui["config_type"] == [CONFIG_TYPE]
    assert f'collect_type = "{COLLECT_TYPE}"' in toml_text
    assert f'config_type = "{CONFIG_TYPE}"' in toml_text
    assert 'brand = "futurematrix"' in toml_text


@pytest.mark.unit
def test_pen_56813_not_2011(toml_text):
    assert PEN in toml_text
    assert HUAWEI_PEN not in toml_text
    for suffix in (
        "5.25.31.1.1.1.1.5",
        "5.25.31.1.1.1.1.7",
        "5.25.31.1.1.1.1.11",
        "5.25.31.1.1.10.1.1",
        "5.25.31.1.1.10.1.7",
        "5.25.31.1.1.3.1.8",
        "5.25.31.1.1.3.1.9",
    ):
        assert f"{PEN}.{suffix}" in toml_text


@pytest.mark.unit
def test_metric_set_matches_huawei_switch(metrics, huawei_metrics):
    names = {m["name"] for m in metrics["metrics"]}
    huawei_names = {m["name"] for m in huawei_metrics["metrics"]}
    assert names == huawei_names
    missing = [h for h in HEALTH if h not in names]
    assert missing == []


@pytest.mark.unit
def test_multi_dim_descr_on_health_metrics(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    for name in MULTI_DIM:
        dims = [d["name"] for d in by[name]["dimensions"]]
        assert dims == ["descr"], f"{name} dimensions={dims}"
        q = by[name]["query"].replace(" ", "")
        assert "by(instance_id)" not in q, f"{name} still collapses by instance_id: {q}"


@pytest.mark.unit
def test_optical_uw_to_dbm_in_query(toml_text, metrics):
    assert "[[processors.starlark]]" not in toml_text
    assert 'name = "device_optical"' in toml_text
    by = {m["name"]: m for m in metrics["metrics"]}
    for name in ("device_optical_rx_power", "device_optical_tx_power"):
        q = by[name]["query"].replace(" ", "")
        assert "10*log10(" in q
        assert "/1000" in q
        assert ">0" in q


@pytest.mark.unit
def test_no_psu_metric(metrics, toml_text):
    names = {m["name"] for m in metrics["metrics"]}
    assert "device_psu_state" not in names
    assert "device_psu" not in toml_text
    assert "18.1.6" not in toml_text  # FMEntityPwrState


@pytest.mark.unit
def test_toml_descr_tags_for_cpu_mem_temp_optical(toml_text):
    assert toml_text.count('name = "descr"') >= 4
    assert "1.3.6.1.2.1.47.1.1.1.1.7" in toml_text


@pytest.mark.unit
def test_plugin_i18n_and_frontend():
    zh = yaml.safe_load((BRAND_DIR / "language" / "zh-Hans.yaml").read_text(encoding="utf-8"))
    en = yaml.safe_load((BRAND_DIR / "language" / "en.yaml").read_text(encoding="utf-8"))
    assert PLUGIN_NAME in zh and PLUGIN_NAME in en
    switch_tsx = (WEB_ROOT / "src/app/monitor/hooks/integration/objects/networkDevice/switch.tsx").read_text(
        encoding="utf-8"
    )
    assert f"'{PLUGIN_NAME}': '{COLLECT_TYPE}'" in switch_tsx
    icons = (WEB_ROOT / "src/app/monitor/utils/common.tsx").read_text(encoding="utf-8")
    assert "/futurematrix/i" in icons
