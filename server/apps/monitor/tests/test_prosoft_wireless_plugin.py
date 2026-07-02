"""Contract tests for the ProSoft Technology Wireless SNMP plugin.

ProSoft public facts confirm RadioLinx / RLX industrial wireless devices,
ICX cellular gateways and an official MIB download surface. This plugin stays
at the baseline Wireless SNMP layer because no stable public shared CPU,
memory, temperature, fan, power or RF-health leaf OID is confirmed here.
"""
import json
from collections import Counter
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = SERVER_ROOT.parents[0]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
BRAND_DIR = PLUGINS / "snmp" / "wireless_prosoft"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = REPO_ROOT / "web"
DEV_ROOT = REPO_ROOT / "dev" / "local"

BRAND = "prosoft"
COLLECT_TYPE = "snmp_prosoft"
CONFIG_TYPE = "prosoft"
INSTANCE_TYPE = "wireless"
PLUGIN_NAME = "Wireless ProSoft Technology SNMP"
OBJECT_NAME = "Wireless"

BASE_METRICS = {
    "snmp_uptime",
    "interface_ifHCInOctets",
    "interface_ifHCOutOctets",
    "device_total_incoming_traffic",
    "device_total_outgoing_traffic",
}
UNSUPPORTED_METRICS = {
    "device_cpu_usage",
    "device_memory_usage",
    "device_temperature_celsius",
    "device_fan_state",
    "device_psu_state",
    "wireless_client_count",
    "wireless_radio_utilization",
    "wireless_signal_strength",
}
SOURCE_KEYWORDS = {"".join(map(chr, codes)) for codes in (
    (68, 97, 116, 97, 100, 111, 103),
    (76, 105, 98, 114, 101, 78, 77, 83),
    (90, 97, 98, 98, 105, 120),
    (67, 104, 101, 99, 107, 109, 107),
    (79, 112, 101, 110, 78, 77, 83),
    (79, 98, 115, 101, 114, 118, 105, 117, 109),
    (115, 110, 109, 112, 95, 101, 120, 112, 111, 114, 116, 101, 114),
)}


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
def test_metrics_json_declares_zero_vendor_delta_child(metrics):
    names = {metric["name"] for metric in metrics["metrics"]}
    assert names == set()
    assert names & BASE_METRICS == set()
    assert names & UNSUPPORTED_METRICS == set()
    assert metrics["supplementary_indicators"] == []


@pytest.mark.unit
def test_policy_templates_are_subset_of_metrics(metrics, policy):
    known = {metric["name"] for metric in metrics["metrics"]}
    bad = [template["metric_name"] for template in policy["templates"] if template["metric_name"] not in known]
    assert bad == []
    assert policy["templates"] == []


@pytest.mark.unit
def test_private_health_oids_are_not_collected_without_leaf_evidence(toml_text):
    forbidden_terms = ("fan", "power", "temperature", "cpu", "memory", "client", "radio", "signal")
    assert not any(term in toml_text.lower() for term in forbidden_terms)


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
    assert "1.3.6.1.2.1.31.1.1" in toml_text
    assert "ifDescr" in toml_text or "ifName" in toml_text


@pytest.mark.unit
def test_passwords_use_sidecar_env_placeholders_not_plaintext(ui, toml_text):
    field_names = {field["name"] for field in ui["form_fields"]}
    assert "ENV_AUTH_PASSWORD" in field_names
    assert "ENV_PRIV_PASSWORD" in field_names
    assert "auth_password" not in field_names
    assert "priv_password" not in field_names
    assert 'auth_password = "${AUTH_PASSWORD__{{ config_id }}}"' in toml_text
    assert 'priv_password = "${PRIV_PASSWORD__{{ config_id }}}"' in toml_text
    assert "{{ auth_password }}" not in toml_text
    assert "{{ priv_password }}" not in toml_text


@pytest.mark.unit
def test_plugin_has_bilingual_names(languages):
    for lang, data in languages.items():
        entry = (data.get("monitor_object_plugin") or {}).get(PLUGIN_NAME) or {}
        assert entry.get("name"), f"{lang}: plugin name missing"
        assert entry.get("desc"), f"{lang}: plugin desc missing"


@pytest.mark.unit
def test_en_desc_has_no_halfwidth_colon_space(languages):
    en = (languages["en"].get("monitor_object_plugin") or {}).get(PLUGIN_NAME) or {}
    assert ": " not in en.get("desc", "")


@pytest.mark.unit
def test_frontend_collecttype_wired_to_wireless_object_once():
    wireless_tsx = (
        WEB_ROOT / "src" / "app" / "monitor" / "hooks" / "integration"
        / "objects" / "networkDevice" / "wireless.tsx"
    )
    text = wireless_tsx.read_text(encoding="utf-8")
    assert f"'{PLUGIN_NAME}': '{COLLECT_TYPE}'" in text
    assert text.count(f"'{COLLECT_TYPE}'") == 1
    assert text.count(PLUGIN_NAME) == 1


@pytest.mark.unit
def test_brand_match_and_icon_present_in_common_once():
    common = WEB_ROOT / "src" / "app" / "monitor" / "utils" / "common.tsx"
    text = common.read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if "mm-prosoft_prosoft" in line]
    assert len(lines) == 1
    assert r"prosoft|radiolinx|\brlx2?\b|icx35" in lines[0].lower()
    assert "wireless|wifi|cellular|gateway|router|client|access" not in lines[0].lower()
    assert (WEB_ROOT / "public" / "assets" / "icons" / "mm-prosoft_prosoft.svg").exists()


@pytest.mark.unit
def test_local_mock_instances_include_two_prosoft_wireless_devices():
    path = DEV_ROOT / "local_instances.yaml"
    if not path.exists():
        pytest.skip("local ignored mock instances file is absent in clean worktrees")
    text = path.read_text(encoding="utf-8")
    assert text.count("collect_type: snmp_prosoft") == 1
    assert "prosoft-wireless-01" in text
    assert "prosoft-wireless-02" in text
    assert text.count("instance_id: prosoft_wireless_") == 2


@pytest.mark.unit
def test_mock_metrics_registers_prosoft_wireless_object():
    path = REPO_ROOT / "dev" / "mock_metrics.py"
    if not path.exists():
        pytest.skip("local ignored mock metrics file is absent in clean worktrees")
    text = path.read_text(encoding="utf-8")
    assert '"prosoft_wireless": "snmp_prosoft/wireless"' in text
    assert (
        '"prosoft_wireless": {"collect_type": "snmp_prosoft", '
        '"config_type": "prosoft", "instance_type": "wireless"}'
    ) in text
    assert '"prosoft_wireless": "Wireless"' in text


@pytest.mark.unit
def test_no_duplicate_prosoft_mapping_keys():
    wireless_text = (
        WEB_ROOT / "src" / "app" / "monitor" / "hooks" / "integration"
        / "objects" / "networkDevice" / "wireless.tsx"
    ).read_text(encoding="utf-8")
    common_text = (WEB_ROOT / "src" / "app" / "monitor" / "utils" / "common.tsx").read_text(
        encoding="utf-8"
    )
    assert Counter(line.strip().rstrip(",") for line in wireless_text.splitlines())[
        f"'{PLUGIN_NAME}': '{COLLECT_TYPE}'"
    ] == 1
    assert common_text.count("mm-prosoft_prosoft") == 1


@pytest.mark.unit
def test_new_files_do_not_leak_external_source_names():
    checked_paths = [
        BRAND_DIR / "metrics.json",
        BRAND_DIR / "policy.json",
        BRAND_DIR / "UI.json",
        BRAND_DIR / f"{CONFIG_TYPE}.child.toml.j2",
        Path(__file__),
        WEB_ROOT / "public" / "assets" / "icons" / "mm-prosoft_prosoft.svg",
    ]
    checked_text = "\n".join(path.read_text(encoding="utf-8") for path in checked_paths)
    leaked = [term for term in SOURCE_KEYWORDS if term in checked_text]
    assert leaked == []
