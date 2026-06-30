"""Contract tests for the RELIANOID loadbalance SNMP plugin.

RELIANOID ADCs currently have a verified baseline profile only: standard MIB-II
uptime plus IF-MIB interface metrics, including 64-bit ifHC counters. The
available state confirms enterprise PEN 61269 for application-layer objects,
but no stable vendor-specific scalar health gauges for CPU, memory,
temperature, fan or power state. The plugin must therefore be a zero-delta
Loadbalance child that relies on the shared SNMP floor.
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
PLUGIN_DIR = PLUGINS / "snmp" / "loadbalance_relianoid"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "relianoid"
COLLECT_TYPE = "snmp_relianoid"
CONFIG_TYPE = "relianoid"
INSTANCE_TYPE = "loadbalance"
PLUGIN_NAME = "Loadbalance RELIANOID SNMP"
OBJECT_NAME = "Loadbalance"
PRIVATE_PEN_ROOT = "1.3.6.1.4.1.61269"

HEALTH_METRICS = (
    "device_cpu_usage",
    "device_memory_used",
    "device_memory_free",
    "device_memory_usage",
    "device_temperature_celsius",
    "device_fan_state",
    "device_psu_state",
    "lb_current_connections",
)
BASE_METRICS = {
    "snmp_uptime",
    "interface_ifAdminStatus",
    "interface_ifOperStatus",
    "interface_ifSpeed",
    "interface_ifInErrors",
    "interface_ifOutErrors",
    "interface_ifInDiscards",
    "interface_ifOutDiscards",
    "interface_ifInUcastPkts",
    "interface_ifOutUcastPkts",
    "interface_ifInOctets",
    "interface_ifOutOctets",
    "interface_ifHCInOctets",
    "interface_ifHCOutOctets",
    "device_total_incoming_traffic",
    "device_total_outgoing_traffic",
}


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def metrics():
    return _read_json(PLUGIN_DIR / "metrics.json")


@pytest.fixture(scope="module")
def policy():
    return _read_json(PLUGIN_DIR / "policy.json")


@pytest.fixture(scope="module")
def ui():
    return _read_json(PLUGIN_DIR / "UI.json")


@pytest.fixture(scope="module")
def toml_text():
    return (PLUGIN_DIR / f"{CONFIG_TYPE}.child.toml.j2").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def languages():
    return {
        lang: yaml.safe_load((LANGUAGE_DIR / f"{lang}.yaml").read_text(encoding="utf-8"))
        for lang in ("zh-Hans", "en")
    }


@pytest.mark.unit
def test_plugin_lives_under_correct_dir(metrics):
    assert metrics["collect_type"] == COLLECT_TYPE
    assert PLUGIN_DIR.parent.name == "snmp"


@pytest.mark.unit
def test_toml_filename_follows_convention():
    assert (PLUGIN_DIR / f"{CONFIG_TYPE}.child.toml.j2").exists()


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
def test_metrics_json_is_zero_delta_child(metrics):
    assert metrics["metrics"] == []
    assert metrics["supplementary_indicators"] == []


@pytest.mark.unit
def test_metrics_json_does_not_redeclare_snmp_floor(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    leaked = sorted(names & BASE_METRICS)
    assert leaked == [], f"SNMP floor metrics must stay in generic snmp/loadbalance: {leaked}"


@pytest.mark.unit
def test_no_private_health_metrics_modelled(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    present = [h for h in HEALTH_METRICS if h in names]
    assert present == [], f"RELIANOID baseline plugin must not model private health metrics: {present}"


@pytest.mark.unit
def test_no_enum_processor_block(toml_text):
    assert "[[processors.enum]]" not in toml_text


@pytest.mark.unit
def test_no_private_pen_oid_used(toml_text):
    assert PRIVATE_PEN_ROOT not in toml_text


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
def test_supplementary_indicators_have_no_dangling_refs(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    dangling = [s for s in metrics.get("supplementary_indicators", []) if s not in names]
    assert dangling == [], f"supplementary_indicators reference absent metrics: {dangling}"


@pytest.mark.unit
def test_policy_templates_reference_existing_metrics(metrics, policy):
    known = {m["name"] for m in metrics["metrics"]}
    bad = [t["metric_name"] for t in policy["templates"] if t["metric_name"] not in known]
    assert bad == [], f"policy references unknown metrics: {bad}"


@pytest.mark.unit
def test_policy_has_no_brand_level_templates(policy):
    assert policy["templates"] == []


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
def test_frontend_collecttype_wired_to_loadbalance_object():
    tsx = (
        WEB_ROOT / "src" / "app" / "monitor" / "hooks" / "integration"
        / "objects" / "networkDevice" / "loadbalance.tsx"
    )
    text = tsx.read_text(encoding="utf-8")
    assert f"'{PLUGIN_NAME}': '{COLLECT_TYPE}'" in text


@pytest.mark.unit
def test_brand_match_present_in_common():
    common = WEB_ROOT / "src" / "app" / "monitor" / "utils" / "common.tsx"
    assert BRAND in common.read_text(encoding="utf-8").lower()


@pytest.mark.unit
def test_shared_dashboard_no_brand_special_case():
    config_ts = (
        WEB_ROOT / "src" / "app" / "monitor" / "dashboards"
        / "objects" / "loadbalance" / "config.ts"
    )
    assert BRAND not in config_ts.read_text(encoding="utf-8").lower()


@pytest.mark.unit
def test_brand_icon_asset_present():
    icon = WEB_ROOT / "public" / "assets" / "icons" / "mm-relianoid_relianoid.svg"
    assert icon.exists()


@pytest.mark.unit
def test_passwords_use_template_vars_not_plaintext(toml_text):
    for field in ("auth_password", "priv_password"):
        assert f'{field} = "{{{{ {field} }}}}"' in toml_text
