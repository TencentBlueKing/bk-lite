"""Contract tests for the Siklu transmission SNMP plugin.

Siklu Radio Bridge devices use enterprise PEN 31926. This plugin promotes only
the verified row-filter-free system temperature scalar into shared Transmission
health. RF signal, CINR, Tx power and per-radio states remain link telemetry and
are not declared as shared device-health metrics in this pass.
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
BRAND_DIR = PLUGINS / "snmp" / "transmission_siklu"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "siklu"
COLLECT_TYPE = "snmp_siklu"
CONFIG_TYPE = "siklu"
INSTANCE_TYPE = "transmission"
PLUGIN_NAME = "Transmission Siklu SNMP"
OBJECT_NAME = "Transmission"
PEN_ROOT = "1.3.6.1.4.1.31926"
TEMP_OID = "1.3.6.1.4.1.31926.1.2.0"

EXPECTED_METRICS = {"device_temperature_celsius"}
ABSENT_METRICS = (
    "snmp_uptime", "interface_ifHCInOctets", "interface_ifHCOutOctets",
    "device_total_incoming_traffic", "device_total_outgoing_traffic",
    "device_cpu_usage", "device_memory_usage", "device_memory_total",
    "device_memory_free", "device_memory_used", "device_fan_state",
    "device_psu_state",
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
    assert not any(field["name"] == "brand" for field in ui["form_fields"])


@pytest.mark.unit
def test_metrics_is_vendor_delta_child(metrics):
    names = {metric["name"] for metric in metrics["metrics"]}
    assert names == EXPECTED_METRICS
    assert all(name not in names for name in ABSENT_METRICS)
    assert metrics["supplementary_indicators"] == ["device_temperature_celsius"]


@pytest.mark.unit
def test_temperature_metric_contract(metrics):
    metric = metrics["metrics"][0]
    assert metric["name"] == "device_temperature_celsius"
    assert metric["unit"] == "celsius"
    assert metric["metric_group"] == "Temperature"
    assert metric["data_type"] == "Number"
    assert metric["dimensions"] == []
    assert metric["query"].startswith("max(")


@pytest.mark.unit
def test_policy_templates_reference_existing_metrics(metrics, policy):
    known = {metric["name"] for metric in metrics["metrics"]}
    assert {template["metric_name"] for template in policy["templates"]} == known


@pytest.mark.unit
def test_private_temperature_oid_collected_without_fabricated_health(toml_text):
    assert PEN_ROOT in toml_text
    assert TEMP_OID in toml_text
    for name in ("device_cpu", "device_memory", "device_fan", "device_psu"):
        assert name not in toml_text
    assert "[[processors.enum]]" not in toml_text


@pytest.mark.unit
def test_temperature_oid_has_no_scaling(toml_text, metrics):
    assert "/10" not in toml_text
    assert "/100" not in toml_text
    query = metrics["metrics"][0]["query"]
    assert "/10" not in query and "/100" not in query


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
def test_toml_collects_iftable_and_uptime(toml_text):
    assert "1.3.6.1.2.1.1.3.0" in toml_text
    assert "1.3.6.1.2.1.2.2" in toml_text
    assert "ifDescr" in toml_text


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
def test_metric_has_bilingual_translation(metrics, languages):
    for lang, data in languages.items():
        metrics_i18n = (data.get("monitor_object_metric") or {}).get(OBJECT_NAME) or {}
        for metric in metrics["metrics"]:
            entry = metrics_i18n.get(metric["name"]) or {}
            assert entry.get("name"), f'{lang}: {metric["name"]} name missing'
            assert entry.get("desc"), f'{lang}: {metric["name"]} desc missing'


@pytest.mark.unit
def test_metric_group_translated(languages):
    for lang, data in languages.items():
        groups = (data.get("monitor_object_metric_group") or {}).get(OBJECT_NAME) or {}
        assert "Temperature" in groups, f"{lang}: Temperature group missing"


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
    assert "siklu" in text
    assert "etherhaul" in text
    assert "mm-siklu_siklu" in text


@pytest.mark.unit
def test_brand_icon_asset_present():
    assert (WEB_ROOT / "public" / "assets" / "icons" / "mm-siklu_siklu.svg").exists()


@pytest.mark.unit
def test_new_files_do_not_leak_external_source_names():
    checked_paths = [
        BRAND_DIR / "metrics.json",
        BRAND_DIR / "policy.json",
        BRAND_DIR / "UI.json",
        BRAND_DIR / f"{CONFIG_TYPE}.child.toml.j2",
        Path(__file__),
        WEB_ROOT / "public" / "assets" / "icons" / "mm-siklu_siklu.svg",
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
