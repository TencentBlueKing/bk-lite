"""Contract tests for the ZDNS network-service SNMP plugin.

ZDNS DNS/GSLB appliances expose two useful trees: F5 BIG-IP LTM service status
under PEN 3375 and ZDNS private scalar health under PEN 39810. The
NetworkService plugin maps clean device health
signals to shared metrics and normalizes service-state enums to 1=healthy /
2=fault. Business counters such as query success rate and cache hit rate are
not treated as device-health metrics.

The brand metrics.json is a child delta: shared SNMP uptime, IF-MIB HC traffic
and device_total_* rollups are collected in the template / common base, but are
not redeclared as ZDNS-specific metric metadata.
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
BRAND_DIR = PLUGINS / "snmp" / "network_service_zdns"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "zdns"
COLLECT_TYPE = "snmp_zdns"
CONFIG_TYPE = "zdns"
INSTANCE_TYPE = "network_service"
PLUGIN_NAME = "NetworkService ZDNS SNMP"
OBJECT_NAME = "NetworkService"
ZDNS_PEN = "1.3.6.1.4.1.39810"
F5_LTM_PEN = "1.3.6.1.4.1.3375.2.2"

HEALTH_METRICS = (
    "device_cpu_usage",
    "device_memory_usage",
    "device_temperature_celsius",
)
SERVICE_STATE_METRICS = (
    "network_service_dns_service_state",
    "network_service_dhcp_service_state",
    "network_service_ntp_service_state",
    "network_service_zwp_service_state",
    "network_service_tftp_service_state",
    "network_service_virtual_server_state",
    "network_service_node_state",
    "network_service_pool_state",
    "network_service_pool_member_state",
)
BASE_METRICS = (
    "snmp_uptime",
    "interface_ifHCInOctets",
    "interface_ifHCOutOctets",
    "device_total_incoming_traffic",
    "device_total_outgoing_traffic",
)
UNSUPPORTED_BUSINESS_METRICS = (
    "zdns_query_success_rate",
    "zdns_cache_hit_rate",
    "zdns_recursion_count",
    "device_disk_usage",
)


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
def test_uses_zdns_private_and_f5_ltm_oids(toml_text):
    assert ZDNS_PEN in toml_text
    assert F5_LTM_PEN in toml_text
    for oid in ("100.1.1", "100.1.2", "100.1.4", "100.1.5", "100.1.6", "100.1.7", "100.1.12", "100.1.13"):
        assert f"{ZDNS_PEN}.{oid}" in toml_text


@pytest.mark.unit
def test_health_metrics_are_direct_percent_and_celsius(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    for name in ("device_cpu_usage", "device_memory_usage"):
        assert by[name]["unit"] == "percent"
        q = by[name]["query"].replace(" ", "")
        assert q.startswith("avg(") and "by(instance_id)" in q
    assert by["device_temperature_celsius"]["unit"] == "celsius"
    assert by["device_temperature_celsius"]["query"].replace(" ", "").startswith("max(")


@pytest.mark.unit
def test_service_state_metrics_are_enums(metrics, toml_text):
    by = {m["name"]: m for m in metrics["metrics"]}
    for name in SERVICE_STATE_METRICS:
        assert name in by
        assert by[name]["data_type"] == "Enum"
        assert by[name]["unit"] == "none"
        assert by[name]["query"].replace(" ", "").startswith("max(")
    for name in SERVICE_STATE_METRICS:
        assert name.removesuffix("_state") in toml_text
    assert "[[processors.enum.mapping]]" in toml_text
    assert 'dest = "state"' in toml_text
    assert "default = 2" in toml_text


@pytest.mark.unit
def test_business_counters_not_promoted_to_health_metrics(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    for absent in UNSUPPORTED_BUSINESS_METRICS:
        assert absent not in names


@pytest.mark.unit
def test_metrics_json_is_brand_delta_without_base_metrics(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    leaked = [name for name in BASE_METRICS if name in names]
    assert leaked == [], f"ZDNS child metrics.json must not redeclare base metrics: {leaked}"


@pytest.mark.unit
def test_toml_collects_uptime_and_64bit_ifhc_counters(toml_text):
    assert "1.3.6.1.2.1.1.3.0" in toml_text
    assert "1.3.6.1.2.1.31.1.1.1.6" in toml_text
    assert "1.3.6.1.2.1.31.1.1.1.10" in toml_text
    assert "1.3.6.1.2.1.2.2.1.10" not in toml_text


@pytest.mark.unit
def test_supplementary_indicators_do_not_reference_base_metrics(metrics):
    leaked = [s for s in metrics.get("supplementary_indicators", []) if s in BASE_METRICS]
    assert leaked == []


@pytest.mark.unit
def test_supplementary_indicators_have_no_dangling_refs(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    dangling = [s for s in metrics.get("supplementary_indicators", []) if s not in names]
    assert dangling == []


@pytest.mark.unit
def test_policy_templates_reference_existing_metrics(metrics, policy):
    known = {m["name"] for m in metrics["metrics"]}
    bad = [t["metric_name"] for t in policy["templates"] if t["metric_name"] not in known]
    assert bad == []


@pytest.mark.unit
def test_plugin_and_metrics_have_bilingual_names(languages):
    required_metric_names = set(HEALTH_METRICS) | set(SERVICE_STATE_METRICS)
    for lang, data in languages.items():
        entry = (data.get("monitor_object_plugin") or {}).get(PLUGIN_NAME) or {}
        assert entry.get("name"), f"{lang}: plugin name missing"
        assert entry.get("desc"), f"{lang}: plugin desc missing"
        metric_names = data.get("monitor_object_metric", {}).get(OBJECT_NAME, {})
        missing = [name for name in required_metric_names if name not in metric_names]
        assert missing == [], f"{lang}: NetworkService metrics missing {missing}"


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
def test_passwords_use_sidecar_env_placeholders_not_plaintext(ui, toml_text):
    field_names = {field["name"] for field in ui["form_fields"]}
    assert "ENV_AUTH_PASSWORD" in field_names
    assert "ENV_PRIV_PASSWORD" in field_names
    assert 'auth_password = "${AUTH_PASSWORD__{{ config_id }}}"' in toml_text
    assert 'priv_password = "${PRIV_PASSWORD__{{ config_id }}}"' in toml_text
    assert 'auth_password = "{{ auth_password }}"' not in toml_text
    assert 'priv_password = "{{ priv_password }}"' not in toml_text
