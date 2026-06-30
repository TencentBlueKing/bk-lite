"""Contract tests for the VeloCloud/VMware SD-WAN router SNMP plugin.

VeloCloud Edge (IANA PEN 45346) exposes stable private health scalars:
  - CPU    vceCpuUtilPct5min 1.3.6.1.4.1.45346.1.1.2.2.2.1.0 (direct %)
  - memory vceMemUsedPct     1.3.6.1.4.1.45346.1.1.2.2.2.3.0 (direct %)

Link/path tables contain SD-WAN business counters and state, but this shared
Router plugin only models common device-health metrics. IF-MIB traffic remains
in the child TOML for collection and is supplied to the capability matrix by the
generic Router SNMP baseline, so this plugin metrics.json stays a delta child.
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
BRAND_DIR = PLUGINS / "snmp" / "router_velocloud"
BASE_DIR = PLUGINS / "snmp" / "router_bintec"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "velocloud"
COLLECT_TYPE = "snmp_velocloud"
CONFIG_TYPE = "velocloud"
INSTANCE_TYPE = "router"
PLUGIN_NAME = "Router VeloCloud SNMP"
OBJECT_NAME = "Router"
PEN_ROOT = "1.3.6.1.4.1.45346"
CPU_OID = "1.3.6.1.4.1.45346.1.1.2.2.2.1.0"
MEMORY_OID = "1.3.6.1.4.1.45346.1.1.2.2.2.3.0"

SUPPORTED_SCALAR_UNITS = {
    "byteps", "bytes", "counts", "cps", "percent", "celsius", "s", "short",
    "none", "bitps",
}
EXPECTED_METRICS = ("device_cpu_usage", "device_memory_usage")
ABSENT_METRICS = (
    "snmp_uptime", "interface_ifHCInOctets", "interface_ifHCOutOctets",
    "device_fan_state", "device_psu_state", "device_temperature_celsius",
    "device_memory_total", "device_memory_free", "device_memory_used",
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
def test_metrics_is_brand_delta_child(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    assert names == set(EXPECTED_METRICS)
    assert all(name not in names for name in ABSENT_METRICS)
    assert metrics.get("display_fields") in (None, [])


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
    assert drift == [], f"shared-metric drift vs Router baseline: {drift}"


@pytest.mark.unit
def test_cpu_and_memory_are_direct_percent(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    assert by["device_cpu_usage"]["unit"] == "percent"
    assert by["device_cpu_usage"]["metric_group"] == "CPU"
    assert by["device_cpu_usage"]["dimensions"] == []
    assert by["device_memory_usage"]["unit"] == "percent"
    assert by["device_memory_usage"]["metric_group"] == "Memory"
    assert by["device_memory_usage"]["dimensions"] == []
    assert "device_memory_total" not in by["device_memory_usage"]["query"]
    assert "device_memory_free" not in by["device_memory_usage"]["query"]


@pytest.mark.unit
def test_temp_fan_psu_and_memory_pool_not_modelled(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    present = [a for a in ABSENT_METRICS if a in names]
    assert present == [], f"VeloCloud models direct CPU/memory usage only: {present}"


@pytest.mark.unit
def test_no_enum_processor_block(toml_text):
    assert "[[processors.enum]]" not in toml_text


@pytest.mark.unit
def test_private_oids_under_pen_45346(toml_text):
    assert CPU_OID in toml_text
    assert MEMORY_OID in toml_text
    assert PEN_ROOT in toml_text


@pytest.mark.unit
def test_toml_collects_64bit_ifhc_counters(toml_text):
    assert "1.3.6.1.2.1.31.1.1.1.6" in toml_text
    assert "1.3.6.1.2.1.31.1.1.1.10" in toml_text
    assert "ifHCInOctets" in toml_text and "ifHCOutOctets" in toml_text


@pytest.mark.unit
def test_cpu_memory_tables_rename_to_usage(toml_text):
    assert 'name = "device_cpu"' in toml_text
    assert 'name = "device_memory"' in toml_text
    assert 'name = "usage"' in toml_text


@pytest.mark.unit
def test_policy_templates_reference_existing_metrics(metrics, policy):
    known = {m["name"] for m in metrics["metrics"]}
    bad = [t["metric_name"] for t in policy["templates"] if t["metric_name"] not in known]
    assert bad == [], f"policy references unknown metrics: {bad}"


@pytest.mark.unit
def test_policy_covers_cpu_and_memory(policy):
    names = {t["metric_name"] for t in policy["templates"]}
    assert names == {"device_cpu_usage", "device_memory_usage"}


@pytest.mark.unit
def test_supplementary_indicators_have_no_dangling_refs(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    dangling = [
        s for s in metrics.get("supplementary_indicators", [])
        if s not in names and s != "snmp_uptime"
    ]
    assert dangling == [], f"supplementary_indicators reference absent metrics: {dangling}"


@pytest.mark.unit
def test_all_scalar_metric_units_supported(metrics):
    bad = [
        f'{m["name"]}:{m["unit"]}'
        for m in metrics["metrics"]
        if m["data_type"] != "Enum" and m["unit"] not in SUPPORTED_SCALAR_UNITS
    ]
    assert bad == [], f"unsupported units: {bad}"


@pytest.mark.unit
def test_plugin_has_bilingual_name_and_desc(languages):
    for lang, data in languages.items():
        entry = (data.get("monitor_object_plugin") or {}).get(PLUGIN_NAME) or {}
        assert entry.get("name"), f"{lang}: plugin name missing"
        assert entry.get("desc"), f"{lang}: plugin desc missing"


@pytest.mark.unit
def test_english_plugin_desc_has_no_colon_space(languages):
    desc = languages["en"]["monitor_object_plugin"][PLUGIN_NAME]["desc"]
    assert ": " not in desc


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
def test_frontend_collecttype_wired_to_router_object():
    tsx = (
        WEB_ROOT / "src" / "app" / "monitor" / "hooks" / "integration"
        / "objects" / "networkDevice" / "router.tsx"
    )
    assert f"'{PLUGIN_NAME}': '{COLLECT_TYPE}'" in tsx.read_text(encoding="utf-8")


@pytest.mark.unit
def test_frontend_brand_match_registered():
    common = WEB_ROOT / "src" / "app" / "monitor" / "utils" / "common.tsx"
    text = common.read_text(encoding="utf-8").lower()
    assert "velocloud" in text
    assert "vmware" in text


@pytest.mark.unit
def test_brand_icon_asset_present():
    icon = WEB_ROOT / "public" / "assets" / "icons" / "mm-velocloud_velocloud.svg"
    assert icon.exists()


@pytest.mark.unit
def test_passwords_use_sidecar_env_placeholders_not_plaintext(ui, toml_text):
    field_names = {field["name"] for field in ui["form_fields"]}
    assert "ENV_AUTH_PASSWORD" in field_names
    assert "ENV_PRIV_PASSWORD" in field_names
    assert 'auth_password = "${AUTH_PASSWORD__{{ config_id }}}"' in toml_text
    assert 'priv_password = "${PRIV_PASSWORD__{{ config_id }}}"' in toml_text
    assert 'auth_password = "{{ auth_password }}"' not in toml_text
    assert 'priv_password = "{{ priv_password }}"' not in toml_text
