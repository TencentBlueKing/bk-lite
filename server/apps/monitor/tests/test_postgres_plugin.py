"""Contract tests for the Postgres monitoring plugin (Telegraf/database/postgres).

Validates internal consistency of the plugin's support files: every policy
template references a metric that actually exists in metrics.json (otherwise the
alert template cannot be instantiated — Metric lookup in metric_query raises
"metric does not exist"), units belong to the product unit system, every metric
carries the `db` dimension emitted by the Telegraf postgresql input, and every
metric / metric group has bilingual translations.
"""
import json
from pathlib import Path

import pytest
import yaml

SERVER_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_DIR = (
    SERVER_ROOT
    / "apps" / "monitor" / "support-files" / "plugins"
    / "Telegraf" / "database" / "postgres"
)
LANGUAGE_DIR = SERVER_ROOT / "apps" / "monitor" / "language"

# Units supported by the product unit system (apps/monitor/utils/unit_converter.py).
SUPPORTED_UNITS = {
    "byteps", "bytes", "counts", "cps", "d", "gibibytes", "h", "kibibytes",
    "kibyteps", "m", "mebibytes", "ms", "msps", "none", "ns", "pebibytes",
    "percent", "s", "short", "µs",
}
# pg_stat_database-derived metrics carry the per-database `db` label; cluster-wide
# pg_stat_bgwriter metrics (checkpoints/buffers) legitimately have no dimension.
DB_SCOPED_METRICS = {
    "postgresql_blk_write_time",
    "postgresql_active_time",
    "postgresql_sessions_killed",
}


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
def test_policy_templates_reference_existing_metrics(metrics, policy):
    known = {m["name"] for m in metrics["metrics"]}
    bad = [t["metric_name"] for t in policy["templates"] if t["metric_name"] not in known]
    assert bad == [], f"policy references unknown metrics: {bad}"


@pytest.mark.unit
def test_all_metric_units_are_supported(metrics):
    bad = [m["name"] for m in metrics["metrics"] if m["unit"] not in SUPPORTED_UNITS]
    assert bad == [], f"unsupported units on metrics: {bad}"


@pytest.mark.unit
def test_dimensions_are_well_formed(metrics):
    """Every declared dimension must have a name and a description."""
    bad = [
        m["name"]
        for m in metrics["metrics"]
        for d in m.get("dimensions", [])
        if not d.get("name") or not d.get("description")
    ]
    assert bad == [], f"metrics with malformed dimensions: {bad}"


@pytest.mark.unit
def test_db_scoped_metrics_carry_db_dimension(metrics):
    """pg_stat_database metrics must expose the per-database `db` label."""
    by_name = {m["name"]: m for m in metrics["metrics"]}
    missing = [
        name
        for name in DB_SCOPED_METRICS
        if "db" not in {d["name"] for d in by_name.get(name, {}).get("dimensions", [])}
    ]
    assert missing == [], f"db-scoped metrics missing db dimension: {missing}"


@pytest.mark.unit
def test_every_metric_has_bilingual_translation(metrics, languages):
    missing = []
    for lang, data in languages.items():
        group = (data.get("monitor_object_metric") or {}).get("Postgres") or {}
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
        trans = (data.get("monitor_object_metric_group") or {}).get("Postgres") or {}
        missing += [f"{lang}:{g}" for g in groups if not trans.get(g)]
    assert missing == [], f"metric groups missing translation: {missing}"
