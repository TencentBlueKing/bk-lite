"""Contract tests for the PacketLight transmission SNMP plugin.

PacketLight optical transmission devices (PEN 4515) are modelled as the
Transmission object. The state queue names public PacketLight SL-NE-MIB/SL-SFP-MIB availability, but this
worktree does not contain the raw MIB body needed to pin exact row-filter-free
health OIDs. Keep the plugin conservative: Telegraf collects sysUpTime + IF-MIB
ifXTable 64-bit traffic, while metrics.json stays a zero-delta child because the
shared Transmission SNMP floor owns uptime, interface and aggregate traffic
metadata. Private optical transmission health metrics are N/A.
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
BRAND_DIR = PLUGINS / "snmp" / "transmission_packetlight"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "packetlight"
COLLECT_TYPE = "snmp_packetlight"
CONFIG_TYPE = "packetlight"
INSTANCE_TYPE = "transmission"
PLUGIN_NAME = "Transmission PacketLight SNMP"
OBJECT_NAME = "Transmission"

PRIVATE_PEN_ROOT = "1.3.6.1.4.1.4515"
HEALTH_METRICS = (
    "device_cpu_usage",
    "device_memory_used",
    "device_memory_free",
    "device_memory_usage",
    "device_temperature_celsius",
    "transmission_optical_power",
    "transmission_link_status",
    "wireless_signal_strength",
    "device_fan_state",
    "device_psu_state",
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
def test_metrics_json_is_zero_delta_child(metrics):
    assert metrics["metrics"] == []
    assert metrics["supplementary_indicators"] == []


@pytest.mark.unit
def test_metrics_json_does_not_redeclare_snmp_floor(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    leaked = sorted(names & BASE_METRICS)
    assert leaked == [], f"SNMP floor metrics must stay in generic snmp/transmission only: {leaked}"


@pytest.mark.unit
def test_no_private_health_metrics_without_exact_oid_source(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    for absent in HEALTH_METRICS:
        assert absent not in names, f"{absent} needs verified PacketLight OID source -> N/A"


@pytest.mark.unit
def test_no_enum_processor_block(toml_text):
    assert "[[processors.enum]]" not in toml_text


@pytest.mark.unit
def test_no_private_pen_oid_used(toml_text):
    assert PRIVATE_PEN_ROOT not in toml_text


@pytest.mark.unit
def test_toml_collects_64bit_ifx_table_and_uptime(toml_text):
    assert "1.3.6.1.2.1.1.3.0" in toml_text
    assert "1.3.6.1.2.1.31.1.1" in toml_text
    assert "1.3.6.1.2.1.31.1.1.1.1" in toml_text
    assert "1.3.6.1.2.1.31.1.1.1.6" in toml_text
    assert "1.3.6.1.2.1.31.1.1.1.10" in toml_text


@pytest.mark.unit
def test_supplementary_indicators_have_no_dangling_refs(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    dangling = [s for s in metrics.get("supplementary_indicators", []) if s not in names]
    assert dangling == []


@pytest.mark.unit
def test_policy_templates_reference_existing_metrics(metrics, policy):
    known = {m["name"] for m in metrics["metrics"]}
    bad = [t["metric_name"] for t in policy.get("templates", []) if t["metric_name"] not in known]
    assert bad == []


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
def test_frontend_collecttype_wired_to_transmission_object():
    transmission_tsx = (
        WEB_ROOT / "src" / "app" / "monitor" / "hooks" / "integration"
        / "objects" / "networkDevice" / "transmission.tsx"
    )
    text = transmission_tsx.read_text(encoding="utf-8")
    assert f"'{PLUGIN_NAME}': '{COLLECT_TYPE}'" in text


@pytest.mark.unit
def test_brand_match_present_in_common():
    common = WEB_ROOT / "src" / "app" / "monitor" / "utils" / "common.tsx"
    assert BRAND in common.read_text(encoding="utf-8")


@pytest.mark.unit
def test_passwords_use_template_vars_not_plaintext(toml_text):
    assert 'auth_password = "${AUTH_PASSWORD__{{ config_id }}}"' in toml_text
    assert 'priv_password = "${PRIV_PASSWORD__{{ config_id }}}"' in toml_text


@pytest.mark.unit
def test_ui_password_fields_use_secret_env_names(ui):
    field_names = {field["name"] for field in ui["form_fields"]}
    assert "ENV_AUTH_PASSWORD" in field_names
    assert "ENV_PRIV_PASSWORD" in field_names
    assert "auth_password" not in field_names
    assert "priv_password" not in field_names
