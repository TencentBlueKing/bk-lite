"""Contract tests for the Stormshield SNS firewall SNMP plugin.

Validated against the generic **firewall** baseline (Telegraf/snmp/firewall),
NOT the Cisco switch baseline. Stormshield must be a strict superset of the
firewall baseline (every baseline interface/uptime metric present with
byte-identical metric_group/unit/query) plus Stormshield-specific health and
firewall state:

  - device_cpu_usage   = avg(...) by (instance_id)  (percent; per-core
                         HOST-RESOURCES hrProcessorLoad aggregated to a single
                         multi-core headline value)
  - device_memory_total / device_memory_free        (KB*1024 -> bytes)
  - device_memory_used  = (total-free)*1024          (bytes, computed inline)
  - device_memory_usage = 100*(total-free)/total     (percent, computed inline)
  - firewall_tcp_connections / firewall_udp_connections  (ASQ engine, short)
  - firewall_vpn_tunnels                              (mature VPN tunnels, short)
  - interface_ifHCInOctets / ifHCOutOctets            (64-bit HC traffic)

Temperature / fan / PSU and HA are intentionally N/A (Firewall object has no
env-sensor display slot; HA is a walk table) — none are modelled and there is
no enum processor. The collectType must wire into the firewall object, not the
switch.

OID correctness is intentionally NOT tested here (pending on-site SNMP walk).
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGINS = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
SS_DIR = PLUGINS / "snmp" / "firewall_stormshield"
BASE_DIR = PLUGINS / "snmp" / "firewall"
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"
WEB_ROOT = SERVER_ROOT.parents[0] / "web"

BRAND = "stormshield"
COLLECT_TYPE = "snmp_stormshield"
CONFIG_TYPE = "stormshield"
INSTANCE_TYPE = "firewall"
PLUGIN_NAME = "Firewall Stormshield SNMP"
OBJECT_NAME = "Firewall"

SUPPORTED_SCALAR_UNITS = {
    "byteps", "bytes", "bitps", "counts", "cps", "percent", "celsius",
    "s", "short", "none",
}
SS_HEALTH = (
    "device_cpu_usage", "device_memory_total", "device_memory_free",
    "device_memory_used", "device_memory_usage",
    "firewall_tcp_connections", "firewall_udp_connections", "firewall_vpn_tunnels",
)
INTERFACE_HC = ("interface_ifHCInOctets", "interface_ifHCOutOctets")
ABSENT_METRICS = (
    "device_temperature_celsius", "device_fan_state", "device_psu_state",
    "firewall_ha_mode",
)


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def metrics():
    return _read_json(SS_DIR / "metrics.json")


@pytest.fixture(scope="module")
def base_metrics():
    return _read_json(BASE_DIR / "metrics.json")


@pytest.fixture(scope="module")
def policy():
    return _read_json(SS_DIR / "policy.json")


@pytest.fixture(scope="module")
def ui():
    return _read_json(SS_DIR / "UI.json")


@pytest.fixture(scope="module")
def toml_text():
    return (SS_DIR / "stormshield.child.toml.j2").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def languages():
    return {
        lang: yaml.safe_load((LANGUAGE_DIR / f"{lang}.yaml").read_text(encoding="utf-8"))
        for lang in ("zh-Hans", "en")
    }


# --------------------------------------------------------------------------- #
# directory / cross-file identity — firewall object, NOT switch
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_plugin_lives_under_firewall_dir(metrics):
    assert metrics["collect_type"] == COLLECT_TYPE  # 身份来自 metrics.json(#3590 解耦)
    assert SS_DIR.parent.name == "snmp"  # 扁平布局


@pytest.mark.unit
def test_toml_filename_follows_convention():
    assert (SS_DIR / f"{CONFIG_TYPE}.child.toml.j2").exists()


@pytest.mark.unit
def test_collect_type_and_object_consistent(metrics, policy, ui, toml_text):
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
def test_object_is_firewall_not_switch(metrics):
    assert metrics["name"] == "Firewall"
    assert all("instance_type='switch'" not in m["query"] for m in metrics["metrics"])


@pytest.mark.unit
def test_config_type_consistent(ui, toml_text):
    assert ui["config_type"] == [CONFIG_TYPE]
    assert f'config_type = "{CONFIG_TYPE}"' in toml_text
    assert f'brand = "{BRAND}"' in toml_text


@pytest.mark.unit
def test_ui_is_pure_snmp_form(ui):
    assert not any(f["name"] == "brand" for f in ui["form_fields"])


# --------------------------------------------------------------------------- #
# superset of the firewall baseline — zero drift on shared metrics
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_is_superset_of_firewall_baseline(metrics, base_metrics):
    ss = {m["name"] for m in metrics["metrics"]}
    base = {m["name"] for m in base_metrics["metrics"]}
    missing = base - ss
    assert missing == set(), f"stormshield dropped baseline firewall metrics: {missing}"


@pytest.mark.unit
def test_shared_metrics_byte_identical_to_baseline(metrics, base_metrics):
    base = {m["name"]: m for m in base_metrics["metrics"]}
    drift = []
    for m in metrics["metrics"]:
        b = base.get(m["name"])
        if b is None:
            continue
        for field in ("metric_group", "unit", "query"):
            if m[field] != b[field]:
                drift.append(f'{m["name"]}.{field}')
    assert drift == [], f"shared-metric drift vs firewall baseline: {drift}"


# --------------------------------------------------------------------------- #
# Stormshield-specific health / memory model / connections
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_stormshield_health_metrics_present(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    missing = [m for m in SS_HEALTH if m not in names]
    assert missing == [], f"stormshield health metrics missing: {missing}"


@pytest.mark.unit
def test_cpu_usage_is_avg_aggregated_percent(metrics):
    """Per-core hrProcessorLoad is aggregated to a single multi-core headline
    via avg(...) by (instance_id)."""
    cpu = {m["name"]: m for m in metrics["metrics"]}["device_cpu_usage"]
    assert cpu["unit"] == "percent"
    q = cpu["query"].replace(" ", "")
    assert q.startswith("avg(") and "by(instance_id)" in q, \
        "multi-core CPU must be averaged per instance"


@pytest.mark.unit
def test_memory_total_and_free_are_bytes_scaled_from_kb(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    for name in ("device_memory_total", "device_memory_free"):
        assert by[name]["unit"] == "bytes", f"{name} must be bytes"
        assert "*1024" in by[name]["query"], f"{name} is KB and must be scaled to bytes"


@pytest.mark.unit
def test_memory_used_is_total_minus_free_scaled(metrics):
    used = {m["name"]: m for m in metrics["metrics"]}["device_memory_used"]
    assert used["unit"] == "bytes"
    q = used["query"].replace(" ", "")
    assert "device_memory_total" in q and "-device_memory_free" in q
    assert "*1024" in q


@pytest.mark.unit
def test_memory_usage_is_computed_percent_inline(metrics):
    usage = {m["name"]: m for m in metrics["metrics"]}["device_memory_usage"]
    assert usage["unit"] == "percent"
    q = usage["query"].replace(" ", "")
    assert q.startswith("100*("), "memory_usage must be computed inline as a percentage"
    assert "device_memory_total" in q and "device_memory_free" in q


@pytest.mark.unit
def test_connection_counters_are_short(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    for name in ("firewall_tcp_connections", "firewall_udp_connections", "firewall_vpn_tunnels"):
        assert by[name]["unit"] == "short", f"{name} must use the short count unit"
        assert by[name]["data_type"] == "Number"


@pytest.mark.unit
def test_interface_hc_metrics_present(metrics):
    by = {m["name"]: m for m in metrics["metrics"]}
    for name in INTERFACE_HC:
        assert name in by, f"{name} must be declared"
        assert by[name]["metric_group"] == "Traffic"
        assert by[name]["unit"] == "byteps"


# --------------------------------------------------------------------------- #
# N/A sensors / not-modelled-as-capability checks
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_absent_metrics_not_modelled(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    present = [a for a in ABSENT_METRICS if a in names]
    assert present == [], f"these are N/A on this plugin and must not be modelled: {present}"


@pytest.mark.unit
def test_no_enum_processor_in_toml(toml_text):
    assert "[[processors.enum]]" not in toml_text


# --------------------------------------------------------------------------- #
# policy / supplementary / display_fields hygiene
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_policy_templates_reference_existing_metrics(metrics, policy):
    known = {m["name"] for m in metrics["metrics"]}
    bad = [t["metric_name"] for t in policy["templates"] if t["metric_name"] not in known]
    assert bad == [], f"policy references unknown metrics: {bad}"


@pytest.mark.unit
def test_supplementary_indicators_have_no_dangling_refs(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    dangling = [s for s in metrics.get("supplementary_indicators", []) if s not in names]
    assert dangling == [], f"supplementary_indicators reference absent metrics: {dangling}"


@pytest.mark.unit
def test_display_fields_have_no_dangling_refs(metrics):
    names = {m["name"] for m in metrics["metrics"]}
    dangling = [
        f["metric"]
        for d in metrics.get("display_fields", [])
        for f in d.get("metrics", [])
        if f["metric"] not in names
    ]
    assert dangling == [], f"display_fields reference absent metrics: {dangling}"


@pytest.mark.unit
def test_no_dangling_descr_in_alert_names(policy):
    for t in policy["templates"]:
        assert "${metric_descr}" not in t["alert_name"], f"{t['metric_name']} dangling descr"


@pytest.mark.unit
def test_all_scalar_metric_units_supported(metrics):
    bad = [
        f'{m["name"]}:{m["unit"]}'
        for m in metrics["metrics"]
        if m["data_type"] != "Enum" and m["unit"] not in SUPPORTED_SCALAR_UNITS
    ]
    assert bad == [], f"unsupported units: {bad}"


@pytest.mark.unit
def test_dimensions_well_formed(metrics):
    bad = [
        m["name"]
        for m in metrics["metrics"]
        for d in m.get("dimensions", [])
        if not d.get("name") or not d.get("description")
    ]
    assert bad == [], f"malformed dimensions: {bad}"


# --------------------------------------------------------------------------- #
# i18n completeness (zh-Hans + en)
# --------------------------------------------------------------------------- #
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
        for m in metrics["metrics"]:
            entry = group.get(m["name"]) or {}
            if not entry.get("name") or not entry.get("desc"):
                missing.append(f'{lang}:{m["name"]}')
    assert missing == [], f"metrics missing translation: {missing}"


@pytest.mark.unit
def test_every_metric_group_has_bilingual_translation(metrics, languages):
    groups = {m["metric_group"] for m in metrics["metrics"]}
    missing = []
    for lang, data in languages.items():
        trans = (data.get("monitor_object_metric_group") or {}).get(OBJECT_NAME) or {}
        missing += [f"{lang}:{g}" for g in groups if not trans.get(g)]
    assert missing == [], f"metric groups missing translation: {missing}"


@pytest.mark.unit
def test_object_has_bilingual_translation(languages):
    for lang, data in languages.items():
        obj = (data.get("monitor_object") or {}).get(OBJECT_NAME)
        assert obj, f"{lang}: object {OBJECT_NAME} missing translation"


# --------------------------------------------------------------------------- #
# frontend wiring: collectType maps into the firewall object, not switch
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_frontend_collecttype_wired_to_firewall_object():
    firewall_tsx = (
        WEB_ROOT / "src" / "app" / "monitor" / "hooks" / "integration"
        / "objects" / "networkDevice" / "firewall.tsx"
    )
    text = firewall_tsx.read_text(encoding="utf-8")
    assert f"'{PLUGIN_NAME}': '{COLLECT_TYPE}'" in text


@pytest.mark.unit
def test_frontend_collecttype_not_wired_to_switch_object():
    switch_tsx = (
        WEB_ROOT / "src" / "app" / "monitor" / "hooks" / "integration"
        / "objects" / "networkDevice" / "switch.tsx"
    )
    text = switch_tsx.read_text(encoding="utf-8")
    assert COLLECT_TYPE not in text, "stormshield firewall must not be wired into the switch object"


# --------------------------------------------------------------------------- #
# secrets never inlined as plaintext
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_passwords_use_template_vars_not_plaintext(toml_text):
    for field in ("auth_password", "priv_password"):
        assert f'{field} = "{{{{ {field} }}}}"' in toml_text, f"{field} must be templated"
