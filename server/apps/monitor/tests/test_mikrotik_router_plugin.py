"""Contract tests for the MikroTik RouterOS router SNMP plugin."""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
PLUGIN_DIR = PLUGINS / "snmp" / "router_mikrotik"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "mikrotik"
COLLECT_TYPE = "snmp_mikrotik_router"
CONFIG_TYPE = "mikrotik"
INSTANCE_TYPE = "router"
PLUGIN_NAME = "Router MikroTik SNMP"
OBJECT_NAME = "Router"

EXPECTED_HEALTH_METRICS = {
    "device_cpu_usage",
    "device_memory_used",
    "device_memory_total",
    "device_memory_usage",
    "device_temperature_celsius",
}
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
UNSUPPORTED_HEALTH_METRICS = {
    "device_memory_free",
    "device_fan_state",
    "device_psu_state",
}
SUPPORTED_SCALAR_UNITS = {
    "byteps",
    "bytes",
    "counts",
    "cps",
    "percent",
    "celsius",
    "s",
    "short",
    "none",
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
    assert not any(field["name"] == "brand" for field in ui["form_fields"])


@pytest.mark.unit
def test_metrics_json_declares_only_routeros_health_deltas(metrics):
    names = {metric["name"] for metric in metrics["metrics"]}
    assert names == EXPECTED_HEALTH_METRICS
    leaked_floor = sorted(names & BASE_METRICS)
    assert leaked_floor == [], f"SNMP floor metrics must stay in generic snmp/router: {leaked_floor}"
    leaked_unsupported = sorted(names & UNSUPPORTED_HEALTH_METRICS)
    assert leaked_unsupported == [], f"unsupported health metrics should not be modelled: {leaked_unsupported}"


@pytest.mark.unit
def test_memory_used_total_ordered_before_usage(metrics):
    order = [metric["name"] for metric in metrics["metrics"]]
    index = {name: pos for pos, name in enumerate(order)}
    assert index["device_memory_used"] < index["device_memory_usage"]
    assert index["device_memory_total"] < index["device_memory_usage"]


@pytest.mark.unit
def test_memory_usage_computed_from_used_and_total(metrics):
    usage = {metric["name"]: metric for metric in metrics["metrics"]}["device_memory_usage"]
    assert usage["unit"] == "percent"
    assert "device_memory_used" in usage["query"]
    assert "device_memory_total" in usage["query"]


@pytest.mark.unit
def test_policy_templates_reference_existing_metrics(metrics, policy):
    known = {metric["name"] for metric in metrics["metrics"]}
    bad = [template["metric_name"] for template in policy["templates"] if template["metric_name"] not in known]
    assert bad == [], f"policy references unknown metrics: {bad}"


@pytest.mark.unit
def test_policy_has_only_supported_health_templates(policy):
    assert {template["metric_name"] for template in policy["templates"]} == {
        "device_cpu_usage",
        "device_memory_usage",
        "device_temperature_celsius",
    }


@pytest.mark.unit
def test_all_metric_units_supported(metrics):
    bad = [
        f'{metric["name"]}:{metric["unit"]}'
        for metric in metrics["metrics"]
        if metric["data_type"] != "Enum" and metric["unit"] not in SUPPORTED_SCALAR_UNITS
    ]
    assert bad == [], f"unsupported units: {bad}"


@pytest.mark.unit
def test_toml_collects_64bit_ifhc_counters_without_32bit_traffic_names(toml_text):
    assert "1.3.6.1.2.1.31.1.1.1.6" in toml_text
    assert "1.3.6.1.2.1.31.1.1.1.10" in toml_text
    assert "ifHCInOctets" in toml_text and "ifHCOutOctets" in toml_text
    assert 'name = "ifInOctets"' not in toml_text
    assert 'name = "ifOutOctets"' not in toml_text
    assert 'oid = "1.3.6.1.2.1.2.2.1.10"' not in toml_text
    assert 'oid = "1.3.6.1.2.1.2.2.1.16"' not in toml_text


@pytest.mark.unit
def test_toml_collects_confirmed_routeros_health_oids(toml_text):
    assert "1.3.6.1.2.1.25.3.3.1.2" in toml_text
    assert "1.3.6.1.2.1.25.2.3.1.6.65536" in toml_text
    assert "1.3.6.1.2.1.25.2.3.1.5.65536" in toml_text
    assert "1.3.6.1.4.1.14988.1.1.3.10" in toml_text
    assert "[[processors.enum]]" not in toml_text


@pytest.mark.unit
def test_passwords_use_template_vars_not_plaintext(toml_text):
    assert 'auth_password = "${AUTH_PASSWORD__{{ config_id }}}"' in toml_text
    assert 'priv_password = "${PRIV_PASSWORD__{{ config_id }}}"' in toml_text
    assert "{{ auth_password }}" not in toml_text
    assert "{{ priv_password }}" not in toml_text


@pytest.mark.unit
def test_ui_password_fields_use_secret_env_names(ui):
    field_names = {field["name"] for field in ui["form_fields"]}
    assert "ENV_AUTH_PASSWORD" in field_names
    assert "ENV_PRIV_PASSWORD" in field_names
    assert "auth_password" not in field_names
    assert "priv_password" not in field_names


@pytest.mark.unit
def test_plugin_has_bilingual_name_and_desc(languages):
    for lang, data in languages.items():
        entry = (data.get("monitor_object_plugin") or {}).get(PLUGIN_NAME) or {}
        assert entry.get("name"), f"{lang}: plugin name missing"
        assert entry.get("desc"), f"{lang}: plugin desc missing"


@pytest.mark.unit
def test_every_metric_has_bilingual_translation(metrics, languages):
    missing = []
    for lang, data in languages.items():
        group = (data.get("monitor_object_metric") or {}).get(OBJECT_NAME) or {}
        for metric in metrics["metrics"]:
            entry = group.get(metric["name"]) or {}
            if not entry.get("name") or not entry.get("desc"):
                missing.append(f'{lang}:{metric["name"]}')
    assert missing == [], f"metrics missing translation: {missing}"


@pytest.mark.unit
def test_every_metric_group_has_bilingual_translation(metrics, languages):
    groups = {metric["metric_group"] for metric in metrics["metrics"]}
    missing = []
    for lang, data in languages.items():
        trans = (data.get("monitor_object_metric_group") or {}).get(OBJECT_NAME) or {}
        missing += [f"{lang}:{group}" for group in groups if not trans.get(group)]
    assert missing == [], f"metric groups missing translation: {missing}"


@pytest.mark.unit
def test_en_desc_has_no_halfwidth_colon_space(languages):
    en = (languages["en"].get("monitor_object_plugin") or {}).get(PLUGIN_NAME) or {}
    assert ": " not in en.get("desc", "")


@pytest.mark.unit
def test_frontend_collecttype_wired_to_router_object_once():
    router_tsx = (
        WEB_ROOT / "src" / "app" / "monitor" / "hooks" / "integration"
        / "objects" / "networkDevice" / "router.tsx"
    )
    text = router_tsx.read_text(encoding="utf-8")
    assert f"'{PLUGIN_NAME}': '{COLLECT_TYPE}'" in text
    assert text.count(f"'{PLUGIN_NAME}': '{COLLECT_TYPE}'") == 1
    assert text.count(COLLECT_TYPE) == 1


@pytest.mark.unit
def test_brand_match_present_in_common_without_generic_terms():
    common = WEB_ROOT / "src" / "app" / "monitor" / "utils" / "common.tsx"
    text = common.read_text(encoding="utf-8")
    assert "mikrotik" in text.lower()
    assert "mm-mikrotik_mikrotik" in text
    assert text.count("mm-mikrotik_mikrotik") == 1
    mikrotik_lines = [line.lower() for line in text.splitlines() if "mikrotik" in line.lower()]
    assert mikrotik_lines
    assert all("router|" not in line and "storage|" not in line and "sdh|" not in line and "oms|" not in line for line in mikrotik_lines)
    assert (WEB_ROOT / "public" / "assets" / "icons" / "mm-mikrotik_mikrotik.svg").exists()


@pytest.mark.unit
def test_shared_dashboard_no_brand_special_case():
    config_ts = (
        WEB_ROOT / "src" / "app" / "monitor" / "dashboards"
        / "objects" / "router" / "config.ts"
    )
    assert BRAND not in config_ts.read_text(encoding="utf-8").lower()


@pytest.mark.unit
def test_new_files_do_not_leak_external_source_names():
    checked_paths = [
        PLUGIN_DIR / "metrics.json",
        PLUGIN_DIR / "policy.json",
        PLUGIN_DIR / "UI.json",
        PLUGIN_DIR / f"{CONFIG_TYPE}.child.toml.j2",
        Path(__file__),
        WEB_ROOT / "public" / "assets" / "icons" / "mm-mikrotik_mikrotik.svg",
    ]
    checked_text = "\n".join(path.read_text(encoding="utf-8") for path in checked_paths)
    forbidden_terms = (
        "Data" + "dog",
        "Libre" + "NMS",
        "Zab" + "bix",
        "Check" + "mk",
        "Open" + "NMS",
        "snmp_" + "exporter",
    )
    leaked = [term for term in forbidden_terms if term in checked_text]
    assert leaked == []
