"""Contract tests for the Pulse Secure firewall SNMP plugin.

Pulse Secure / Ivanti Connect Secure (IVE, IANA PEN 12532) exposes scalar health
gauges from PULSESECURE-PSG-MIB:
  - CPU   iveCpuUtil       1.3.6.1.4.1.12532.10.0  (direct %)
  - mem   iveMemoryUtil    1.3.6.1.4.1.12532.11.0  (direct %)
  - swap  iveSwapUtil      1.3.6.1.4.1.12532.24.0  (direct %)
  - disk  diskFullPercent  1.3.6.1.4.1.12532.25.0  (direct %)
  - temp  iveTemperature   1.3.6.1.4.1.12532.42.0  (Celsius, no scaling; MAG only)
  - users signedInWebUsers 1.3.6.1.4.1.12532.2.0   (count)
No fan/PSU objects (N/A) -> no processors.enum block. Memory is reported directly
as a percentage, so there must be NO device_memory_used / device_memory_free.
The object type is Firewall (SSL VPN / ZTNA gateway).
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
BRAND_DIR = PLUGINS / "snmp" / "firewall_pulsesecure"
BASE_DIR = PLUGINS / "snmp" / "firewall_hillstone"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "pulsesecure"
COLLECT_TYPE = "snmp_pulsesecure"
CONFIG_TYPE = "pulsesecure"
INSTANCE_TYPE = "firewall"
PLUGIN_NAME = "Firewall Pulse Secure SNMP"
OBJECT_NAME = "Firewall"
PEN_ROOT = "1.3.6.1.4.1.12532"

SUPPORTED_SCALAR_UNITS = {
    "byteps", "bytes", "counts", "cps", "percent", "celsius", "s", "short",
    "none", "bitps",
}
ABSENT_METRICS = (
    "device_memory_used", "device_memory_free",
    "device_fan_state", "device_psu_state",
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
def test_cpu_is_percent_in_firewall_group(metrics):
    cpu = {m["name"]: m for m in metrics["metrics"]}["device_cpu_usage"]
    assert cpu["unit"] == "percent"
    assert cpu["metric_group"] == "Firewall"
    assert cpu["dimensions"] == []


@pytest.mark.unit
def test_memory_swap_disk_are_direct_percent(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    for name in ("device_memory_usage", "device_swap_usage", "device_disk_usage"):
        assert name in by, f"{name} missing"
        m = by[name]
        assert m["unit"] == "percent"
        assert m["dimensions"] == []
    q = by["device_memory_usage"]["query"].replace(" ", "")
    assert "device_memory_used" not in q and "device_memory_free" not in q


@pytest.mark.unit
def test_temperature_celsius_without_scaling(metrics, toml_text):
    by = {m["name"]: m for m in metrics["metrics"]}
    assert "device_temperature_celsius" in by
    m = by["device_temperature_celsius"]
    assert m["unit"] == "celsius"
    # baseline Firewall parity keeps temperature in the Firewall group
    assert m["metric_group"] == "Firewall"
    q = m["query"].replace(" ", "")
    assert q.startswith("max(") and "by(instance_id)" in q
    assert "/10" not in q, "iveTemperature is already Celsius, must not divide by 10"
    assert 'name = "celsius"' in toml_text


@pytest.mark.unit
def test_web_users_metric_present(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    assert "device_web_users" in by
    assert by["device_web_users"]["data_type"] != "Enum"


@pytest.mark.unit
def test_no_used_free_fan_psu(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    present = [a for a in ABSENT_METRICS if a in names]
    assert present == [], f"Pulse Secure reports mem as %% and has no fan/psu: {present}"


@pytest.mark.unit
def test_no_enum_processor_block(toml_text):
    assert "[[processors.enum]]" not in toml_text


@pytest.mark.unit
def test_private_oids_under_pen_12532(toml_text):
    assert "1.3.6.1.4.1.12532.10.0" in toml_text  # CPU
    assert "1.3.6.1.4.1.12532.11.0" in toml_text  # mem
    assert "1.3.6.1.4.1.12532.24.0" in toml_text  # swap
    assert "1.3.6.1.4.1.12532.25.0" in toml_text  # disk
    assert "1.3.6.1.4.1.12532.42.0" in toml_text  # temp
    assert "1.3.6.1.4.1.12532.2.0" in toml_text   # signed-in web users
    assert PEN_ROOT in toml_text


@pytest.mark.unit
def test_toml_collects_64bit_ifhc_counters(toml_text):
    assert "1.3.6.1.2.1.31.1.1.1.6" in toml_text
    assert "1.3.6.1.2.1.31.1.1.1.10" in toml_text
    assert "ifHCInOctets" in toml_text and "ifHCOutOctets" in toml_text


@pytest.mark.unit
def test_metrics_is_brand_delta_without_baseline_uptime_oid(metrics):
    # uptime metric is allowed but the MIB-II uptime OID must not appear in metrics.json
    assert "1.3.6.1.2.1.1.3.0" not in json.dumps(metrics)


@pytest.mark.unit
def test_policy_templates_reference_existing_metrics(metrics, policy):
    known = {m["name"] for m in metrics["metrics"]}
    bad = [t["metric_name"] for t in policy["templates"] if t["metric_name"] not in known]
    assert bad == [], f"policy references unknown metrics: {bad}"


@pytest.mark.unit
def test_policy_covers_cpu_memory_disk(policy):
    names = {t["metric_name"] for t in policy["templates"]}
    assert {"device_cpu_usage", "device_memory_usage", "device_disk_usage"}.issubset(names)


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
def test_en_desc_has_no_halfwidth_colon_space(languages):
    en = (languages["en"].get("monitor_object_plugin") or {}).get(PLUGIN_NAME) or {}
    assert ": " not in en.get("desc", "")


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
def test_frontend_collecttype_wired_to_firewall_object():
    tsx = (
        WEB_ROOT / "src" / "app" / "monitor" / "hooks" / "integration"
        / "objects" / "networkDevice" / "firewall.tsx"
    )
    assert f"'{PLUGIN_NAME}': '{COLLECT_TYPE}'" in tsx.read_text(encoding="utf-8")


@pytest.mark.unit
def test_frontend_brand_match_registered():
    common = WEB_ROOT / "src" / "app" / "monitor" / "utils" / "common.tsx"
    assert "pulsesecure" in common.read_text(encoding="utf-8").lower()


@pytest.mark.unit
def test_brand_icon_asset_present():
    icon = WEB_ROOT / "public" / "assets" / "icons" / "mm-pulsesecure_pulsesecure.svg"
    assert icon.exists()


@pytest.mark.unit
def test_passwords_use_template_vars_not_plaintext(toml_text):
    for field in ("auth_password", "priv_password"):
        assert f'{field} = "{{{{ {field} }}}}"' in toml_text
