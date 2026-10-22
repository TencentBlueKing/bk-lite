"""SNMP 查询必须按采集器过滤，避免多个模板叠在同一实例上时 sum/count 翻倍。"""

import json
import re
from pathlib import Path

import pytest

from apps.monitor.management.services.plugin_migrate import (
    TEMPLATE_COLLECT_TYPE_PATTERN,
    _IFMIB_METRICS_BY_INSTANCE_TYPE,
    _build_common_ifmib_metrics,
    merge_common_ifmib_metrics,
)
from apps.monitor.utils.snmp_ifmib_capability import COMMON_IFMIB_METRIC_NAMES

SNMP_ROOT = Path(__file__).resolve().parents[1] / "support-files" / "plugins" / "Telegraf" / "snmp"
QUERY_FIELDS = ("query", "view_query", "status_query")
SELECTOR_PATTERN = re.compile(r"\{[^{}]*\}")


def _template_collect_type(plugin_dir: Path) -> str:
    found = []
    for template_path in sorted(plugin_dir.glob("*.child.toml.j2")):
        for declared in TEMPLATE_COLLECT_TYPE_PATTERN.findall(template_path.read_text(encoding="utf-8")):
            declared = declared.strip()
            if not declared or "{" in declared or "}" in declared or declared in found:
                continue
            found.append(declared)
    assert len(found) == 1, f"{plugin_dir.name} collect_type={found}"
    return found[0]


def _iter_queries(plugin_data):
    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in QUERY_FIELDS and isinstance(item, str):
                    yield key, item
                else:
                    yield from walk(item)
        elif isinstance(value, list):
            for item in value:
                yield from walk(item)

    yield from walk(plugin_data)


@pytest.mark.unit
def test_every_snmp_query_filters_its_template_collect_type():
    metrics_files = sorted(SNMP_ROOT.glob("*/metrics.json"))
    assert metrics_files, "expected Telegraf/snmp plugin manifests"
    for metrics_path in metrics_files:
        collect_type = _template_collect_type(metrics_path.parent)
        plugin_data = json.loads(metrics_path.read_text(encoding="utf-8"))
        queries = list(_iter_queries(plugin_data))
        assert queries, f"{metrics_path.parent.name} has no query"
        for field, query in queries:
            for selector in SELECTOR_PATTERN.findall(query):
                if "instance_type" not in selector:
                    continue
                assert f"collect_type='{collect_type}'" in selector, f"{metrics_path.parent.name} {field} selector missing collect_type: {selector}"


@pytest.mark.unit
def test_hillstone_ifmib_merge_filters_snmp_hillstone():
    plugin_dir = SNMP_ROOT / "firewall_hillstone"
    plugin_data = json.loads((plugin_dir / "metrics.json").read_text(encoding="utf-8"))
    merged = merge_common_ifmib_metrics(plugin_data, plugin_dir)
    ifmib_metrics = [metric for metric in merged["metrics"] if metric["name"] in COMMON_IFMIB_METRIC_NAMES]
    assert {metric["name"] for metric in ifmib_metrics} == set(COMMON_IFMIB_METRIC_NAMES)
    for metric in ifmib_metrics:
        assert metric["is_ifmib"] is True
        selectors = [selector for selector in SELECTOR_PATTERN.findall(metric["query"]) if "instance_type" in selector]
        assert selectors, metric["name"]
        for selector in selectors:
            assert "collect_type='snmp_hillstone'" in selector, metric["query"]


@pytest.mark.unit
def test_ifmib_merge_without_template_keeps_instance_type_only():
    merged = merge_common_ifmib_metrics(
        {
            "type": "Network Device",
            "name": "Firewall",
            "collect_type": "snmp_hillstone",
            "metrics": [],
        }
    )
    traffic = next(metric for metric in merged["metrics"] if metric["name"] == "device_total_incoming_traffic")
    assert "collect_type=" not in traffic["query"]
    assert "instance_type='firewall'" in traffic["query"]


@pytest.mark.unit
def test_ifmib_metric_cache_is_keyed_by_collect_type():
    _IFMIB_METRICS_BY_INSTANCE_TYPE.clear()
    generic = _build_common_ifmib_metrics("firewall", "")
    hillstone = _build_common_ifmib_metrics("firewall", "snmp_hillstone")
    generic_again = _build_common_ifmib_metrics("firewall", "")
    assert "collect_type=" not in generic[0]["query"]
    assert "collect_type='snmp_hillstone'" in hillstone[0]["query"]
    assert generic_again[0]["query"] == generic[0]["query"]
    assert ("firewall", "") in _IFMIB_METRICS_BY_INSTANCE_TYPE
    assert ("firewall", "snmp_hillstone") in _IFMIB_METRICS_BY_INSTANCE_TYPE
