"""Contract tests for the 4RF Aprisa transmission SNMP plugin.

AprisaXE devices expose hardware health objects in APRISAXE-MIB-4RF under
enterprise PEN 14817:
  - aprisaXEReceiverTemperature 1.3.6.1.4.1.14817.7.3.1.2.51.8, Celsius
  - aprisaXEFan1Status          1.3.6.1.4.1.14817.7.3.1.2.21.1, fanOkay(1)
  - aprisaXEFan2Status          1.3.6.1.4.1.14817.7.3.1.2.21.2, fanOkay(1)

Uptime and IF-MIB interface traffic are collected by the child TOML but are
supplied to capabilities by the shared Transmission SNMP floor, so metrics.json
stays a vendor-specific delta child.
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
BRAND_DIR = PLUGINS / "snmp" / "transmission_4rf"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "4rf"
COLLECT_TYPE = "snmp_4rf"
CONFIG_TYPE = "4rf"
INSTANCE_TYPE = "transmission"
PLUGIN_NAME = "Transmission 4RF Aprisa SNMP"
OBJECT_NAME = "Transmission"
PEN_ROOT = "1.3.6.1.4.1.14817"
TEMP_OID = "1.3.6.1.4.1.14817.7.3.1.2.51.8"
FAN1_OID = "1.3.6.1.4.1.14817.7.3.1.2.21.1"
FAN2_OID = "1.3.6.1.4.1.14817.7.3.1.2.21.2"

EXPECTED_METRICS = {"device_temperature_celsius", "device_fan_state"}
ABSENT_METRICS = (
    "snmp_uptime", "interface_ifHCInOctets", "interface_ifHCOutOctets",
    "device_total_incoming_traffic", "device_total_outgoing_traffic",
    "device_cpu_usage", "device_memory_usage", "device_memory_total",
    "device_memory_free", "device_memory_used", "device_psu_state",
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
    assert not any(field["name"] == "brand" for field in ui["form_fields"])


@pytest.mark.unit
def test_metrics_is_vendor_delta_child(metrics):
    names = {metric["name"] for metric in metrics["metrics"]}
    assert names == EXPECTED_METRICS
    assert all(name not in names for name in ABSENT_METRICS)
    assert sorted(metrics["supplementary_indicators"]) == sorted(EXPECTED_METRICS)


@pytest.mark.unit
def test_temperature_and_fan_metric_contract(metrics):
    by_name = {metric["name"]: metric for metric in metrics["metrics"]}
    assert by_name["device_temperature_celsius"]["unit"] == "celsius"
    assert by_name["device_temperature_celsius"]["metric_group"] == "Temperature"
    assert by_name["device_temperature_celsius"]["query"].startswith("max(")
    fan = by_name["device_fan_state"]
    assert fan["metric_group"] == "Hardware Status"
    assert fan["data_type"] == "Enum"
    assert {option["id"] for option in json.loads(fan["unit"])} == {1, 2}
    assert fan["query"].startswith("max(")


@pytest.mark.unit
def test_cpu_memory_and_psu_not_modelled(metrics, toml_text):
    names = {metric["name"] for metric in metrics["metrics"]}
    assert "device_cpu_usage" not in names
    assert "device_memory_usage" not in names
    assert "device_psu_state" not in names
    assert "device_cpu" not in toml_text
    assert "device_memory" not in toml_text
    assert "device_psu" not in toml_text


@pytest.mark.unit
def test_private_oids_under_pen_14817(toml_text):
    assert PEN_ROOT in toml_text
    assert TEMP_OID in toml_text
    assert FAN1_OID in toml_text
    assert FAN2_OID in toml_text


@pytest.mark.unit
def test_temperature_oid_has_no_scaling(toml_text, metrics):
    assert "/10" not in toml_text
    assert "/100" not in toml_text
    query = {m["name"]: m["query"] for m in metrics["metrics"]}["device_temperature_celsius"]
    assert "/10" not in query and "/100" not in query


@pytest.mark.unit
def test_enum_processor_normalizes_fan_status_conservatively(toml_text):
    assert "[[processors.enum]]" in toml_text
    assert toml_text.count('namepass = ["device_fan"]') == 2
    assert toml_text.count("default = 2") >= 2
    assert toml_text.count('"0" = 1') >= 2
    assert toml_text.count('"1" = 1') >= 2


@pytest.mark.unit
def test_toml_collects_64bit_ifhc_counters_only_for_traffic(toml_text):
    assert "1.3.6.1.2.1.31.1.1.1.6" in toml_text
    assert "1.3.6.1.2.1.31.1.1.1.10" in toml_text
    assert "ifHCInOctets" in toml_text and "ifHCOutOctets" in toml_text
    assert 'name = "ifInOctets"' not in toml_text
    assert 'name = "ifOutOctets"' not in toml_text
    assert 'oid = "1.3.6.1.2.1.2.2.1.10"' not in toml_text
    assert 'oid = "1.3.6.1.2.1.2.2.1.16"' not in toml_text


@pytest.mark.unit
def test_toml_collects_uptime_and_interface_name(toml_text):
    assert "1.3.6.1.2.1.1.3.0" in toml_text
    assert "ifDescr" in toml_text


@pytest.mark.unit
def test_policy_templates_reference_existing_metrics(metrics, policy):
    known = {metric["name"] for metric in metrics["metrics"]}
    assert {template["metric_name"] for template in policy["templates"]} <= known


@pytest.mark.unit
def test_policy_covers_health_metrics(policy):
    assert {template["metric_name"] for template in policy["templates"]} == EXPECTED_METRICS


@pytest.mark.unit
def test_passwords_use_sidecar_env_placeholders_not_plaintext(ui, toml_text):
    fields = {field["name"]: field for field in ui["form_fields"]}
    assert "ENV_AUTH_PASSWORD" in fields
    assert "ENV_PRIV_PASSWORD" in fields
    assert "auth_password" not in fields
    assert "priv_password" not in fields
    assert fields["ENV_AUTH_PASSWORD"].get("encrypted") is True
    assert fields["ENV_PRIV_PASSWORD"].get("encrypted") is True
    assert fields["ENV_AUTH_PASSWORD"]["transform_on_edit"]["origin_path"] == (
        "child.env_config.AUTH_PASSWORD__{{config_id}}"
    )
    assert fields["ENV_PRIV_PASSWORD"]["transform_on_edit"]["origin_path"] == (
        "child.env_config.PRIV_PASSWORD__{{config_id}}"
    )
    assert 'auth_password = "${AUTH_PASSWORD__{{ config_id }}}"' in toml_text
    assert 'priv_password = "${PRIV_PASSWORD__{{ config_id }}}"' in toml_text
    assert "{{ auth_password }}" not in toml_text
    assert "{{ priv_password }}" not in toml_text


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
    for lang, data in languages.items():
        metrics_i18n = (data.get("monitor_object_metric") or {}).get(OBJECT_NAME) or {}
        for metric in metrics["metrics"]:
            entry = metrics_i18n.get(metric["name"]) or {}
            assert entry.get("name"), f'{lang}: {metric["name"]} name missing'
            assert entry.get("desc"), f'{lang}: {metric["name"]} desc missing'


@pytest.mark.unit
def test_metric_groups_translated(languages):
    for lang, data in languages.items():
        groups = (data.get("monitor_object_metric_group") or {}).get(OBJECT_NAME) or {}
        for group in ("Temperature", "Hardware Status"):
            assert group in groups, f"{lang}: metric group missing {group}"


@pytest.mark.unit
def test_frontend_collecttype_wired_to_transmission_object():
    tsx = (
        WEB_ROOT / "src" / "app" / "monitor" / "hooks" / "integration"
        / "objects" / "networkDevice" / "transmission.tsx"
    )
    assert f"'{PLUGIN_NAME}': '{COLLECT_TYPE}'" in tsx.read_text(encoding="utf-8")


@pytest.mark.unit
def test_frontend_brand_match_registered():
    common = WEB_ROOT / "src" / "app" / "monitor" / "utils" / "common.tsx"
    text = common.read_text(encoding="utf-8").lower()
    assert "4rf" in text
    assert "aprisa" in text
    assert "mm-4rf_4rf" in text


@pytest.mark.unit
def test_brand_icon_asset_present():
    assert (WEB_ROOT / "public" / "assets" / "icons" / "mm-4rf_4rf.svg").exists()


@pytest.mark.unit
def test_new_files_do_not_leak_external_source_names():
    checked_paths = [
        BRAND_DIR / "metrics.json",
        BRAND_DIR / "policy.json",
        BRAND_DIR / "UI.json",
        BRAND_DIR / f"{CONFIG_TYPE}.child.toml.j2",
        Path(__file__),
        WEB_ROOT / "public" / "assets" / "icons" / "mm-4rf_4rf.svg",
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
    assert [term for term in forbidden_terms if term in checked_text] == []
