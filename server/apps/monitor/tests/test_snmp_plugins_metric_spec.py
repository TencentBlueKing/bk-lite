"""Metric-spec regression guard for all SNMP network-device plugins.

Codifies the bk-lite monitoring metric conventions as an executable check so that
producer (loop A) regressions are caught automatically instead of by manual review:

1. Every ``metric_group`` must resolve to a translation key under
   ``monitor_object_metric_group.<Object>`` in BOTH zh-Hans and en language files
   (i.e. no metric may sit in an untranslated group such as the recurring
   ``Environment`` defect, or a wrong-object group such as ``Router`` on a Switch).
2. Every metric ``name`` must have a bilingual entry under
   ``monitor_object_metric.<Object>`` in BOTH language files.
3. An aggregated query (``max/min/avg/sum/count(...) by (...)``) must NOT declare
   the dimensions it aggregates away — declared ``dimensions`` must be empty.

The check parses the support-files directly (no Django/DB needed) so it runs fast
and stays valid regardless of import state.
"""
from __future__ import annotations

import glob
import json
import re
from pathlib import Path

import pytest
import yaml

# repo root = .../server/apps/monitor/tests/<this file> -> up 4 to <repo>/server, up 5 to <repo>
_MONITOR = Path(__file__).resolve().parents[1]  # apps/monitor
_PLUGINS_GLOB = str(_MONITOR / "support-files" / "plugins" / "Telegraf" / "snmp_*" / "*" / "metrics.json")
_LANG = _MONITOR / "language"

_AGG_RE = re.compile(r"\b(?:max|min|avg|sum|count)\s*\(")
_BY_RE = re.compile(r"by\s*\(")


def _load_yaml(name: str) -> dict:
    with open(_LANG / name, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


_ZH = _load_yaml("zh-Hans.yaml")
_EN = _load_yaml("en.yaml")
_ZG = _ZH.get("monitor_object_metric_group", {})
_EG = _EN.get("monitor_object_metric_group", {})
_ZM = _ZH.get("monitor_object_metric", {})
_EM = _EN.get("monitor_object_metric", {})


def _groups(tbl: dict, obj: str) -> set:
    return set((tbl.get(obj) or {}).keys())


def _names(tbl: dict, obj: str) -> set:
    return set((tbl.get(obj) or {}).keys())


def _iter_metrics():
    for path in sorted(glob.glob(_PLUGINS_GLOB)):
        data = json.load(open(path, encoding="utf-8"))
        obj = data.get("name")
        vendor = "/".join(Path(path).parts[-3:-1])
        for metric in data.get("metrics", []):
            yield vendor, obj, metric


_CASES = list(_iter_metrics())
_IDS = [f"{v}:{m['name']}" for v, _o, m in _CASES]


def test_snmp_plugins_discovered():
    assert _CASES, "No SNMP plugin metrics discovered — path resolution is broken"


@pytest.mark.parametrize("vendor,obj,metric", _CASES, ids=_IDS)
def test_metric_group_is_translated(vendor, obj, metric):
    group = metric["metric_group"]
    assert group in _groups(_ZG, obj), (
        f"{vendor}: metric '{metric['name']}' uses metric_group '{group}' "
        f"with no zh-Hans translation under monitor_object_metric_group.{obj}"
    )
    assert group in _groups(_EG, obj), (
        f"{vendor}: metric '{metric['name']}' uses metric_group '{group}' "
        f"with no en translation under monitor_object_metric_group.{obj}"
    )


@pytest.mark.parametrize("vendor,obj,metric", _CASES, ids=_IDS)
def test_metric_name_is_bilingual(vendor, obj, metric):
    name = metric["name"]
    assert name in _names(_ZM, obj), (
        f"{vendor}: metric '{name}' missing zh-Hans entry under monitor_object_metric.{obj}"
    )
    assert name in _names(_EM, obj), (
        f"{vendor}: metric '{name}' missing en entry under monitor_object_metric.{obj}"
    )


@pytest.mark.parametrize("vendor,obj,metric", _CASES, ids=_IDS)
def test_aggregated_metric_has_no_dangling_dimensions(vendor, obj, metric):
    query = metric["query"]
    aggregated = bool(_AGG_RE.search(query)) and bool(_BY_RE.search(query))
    dims = [d["name"] for d in metric.get("dimensions", [])]
    if aggregated:
        assert not dims, (
            f"{vendor}: metric '{metric['name']}' aggregates with by(...) but still "
            f"declares dimensions {dims} that are collapsed away"
        )
