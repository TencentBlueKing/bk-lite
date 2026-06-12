"""Contract tests for the HAProxy monitoring plugin (Telegraf/middleware/haproxy).

Validates internal consistency of the plugin's support files: units are part of
the product unit system, every metric/group/plugin/object has bilingual
translations, policy templates reference real metrics, and metrics carry the
pxname/svname dimensions actually emitted by the Telegraf haproxy input
(keep_field_names=true keeps the raw HAProxy tag names pxname/svname/type/server,
NOT the renamed proxy/sv).
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_DIR = (
    SERVER_ROOT
    / "apps" / "monitor" / "support-files" / "plugins"
    / "Telegraf" / "middleware" / "haproxy"
)
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"

# Units supported by the product unit system (apps/monitor/utils/unit_converter.py).
SUPPORTED_UNITS = {
    "byteps", "bytes", "counts", "cps", "d", "gibibytes", "h", "kibibytes",
    "kibyteps", "m", "mebibytes", "ms", "none", "ns", "pebibytes", "percent", "s",
}
EXPECTED_DIMENSIONS = {"pxname", "svname"}


@pytest.fixture(scope="module")
def metrics():
    return json.loads((PLUGIN_DIR / "metrics.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def policy():
    return json.loads((PLUGIN_DIR / "policy.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def languages():
    return {
        lang: yaml.safe_load((LANGUAGE_DIR / f"{lang}.yaml").read_text(encoding="utf-8"))
        for lang in ("zh-Hans", "en")
    }


@pytest.mark.unit
def test_all_metric_units_are_supported(metrics):
    bad = [m["name"] for m in metrics["metrics"] if m["unit"] not in SUPPORTED_UNITS]
    assert bad == [], f"unsupported units on metrics: {bad}"


@pytest.mark.unit
def test_metrics_carry_pxname_and_svname_dimensions(metrics):
    missing = [
        m["name"]
        for m in metrics["metrics"]
        if {d["name"] for d in m.get("dimensions", [])} != EXPECTED_DIMENSIONS
    ]
    assert missing == [], f"metrics missing pxname/svname dimensions: {missing}"


@pytest.mark.unit
def test_every_metric_has_bilingual_translation(metrics, languages):
    missing = []
    for lang, data in languages.items():
        group = (data.get("monitor_object_metric") or {}).get("Haproxy") or {}
        for m in metrics["metrics"]:
            entry = group.get(m["name"]) or {}
            if not entry.get("name") or not entry.get("desc"):
                missing.append(f"{lang}:{m['name']}")
    assert missing == [], f"metrics missing name/desc translation: {missing}"


@pytest.mark.unit
def test_every_metric_group_has_bilingual_translation(metrics, languages):
    groups = {m["metric_group"] for m in metrics["metrics"]}
    missing = []
    for lang, data in languages.items():
        trans = (data.get("monitor_object_metric_group") or {}).get("Haproxy") or {}
        missing += [f"{lang}:{g}" for g in groups if not trans.get(g)]
    assert missing == [], f"metric groups missing translation: {missing}"


@pytest.mark.unit
def test_plugin_and_object_have_bilingual_translation(languages):
    missing = []
    for lang, data in languages.items():
        plugin = (data.get("monitor_object_plugin") or {}).get("Haproxy") or {}
        if not plugin.get("name") or not plugin.get("desc"):
            missing.append(f"{lang}:plugin")
        if not (data.get("monitor_object") or {}).get("Haproxy"):
            missing.append(f"{lang}:object")
    assert missing == [], f"missing plugin/object translation: {missing}"


@pytest.mark.unit
def test_policy_templates_reference_existing_metrics(metrics, policy):
    known = {m["name"] for m in metrics["metrics"]}
    bad = [t["metric_name"] for t in policy["templates"] if t["metric_name"] not in known]
    assert bad == [], f"policy references unknown metrics: {bad}"
