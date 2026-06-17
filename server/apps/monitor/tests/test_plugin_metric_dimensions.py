import json
from pathlib import Path

import pytest

from apps.monitor.services.plugin import MonitorPluginService


PLUGIN_ROOT = Path(__file__).resolve().parents[1] / "support-files" / "plugins"


def _iter_metrics():
    for metrics_file in PLUGIN_ROOT.rglob("metrics.json"):
        data = json.loads(metrics_file.read_text())
        for metric in data.get("metrics", []):
            yield metrics_file, metric
        for obj in data.get("objects", []):
            for metric in obj.get("metrics", []):
                yield metrics_file, metric


@pytest.mark.unit
def test_all_plugin_metric_dimensions_use_object_shape():
    bad = []
    for metrics_file, metric in _iter_metrics():
        for index, dimension in enumerate(metric.get("dimensions", [])):
            if not isinstance(dimension, dict) or not dimension.get("name"):
                bad.append(
                    f"{metrics_file}:{metric.get('name')}[{index}]={dimension!r}"
                )

    assert bad == []


@pytest.mark.unit
def test_normalize_metric_dimensions_converts_legacy_strings_and_drops_empty_values():
    assert MonitorPluginService.normalize_metric_dimensions(
        ["device", {"name": "interface"}, "", None]
    ) == [
        {"name": "device"},
        {"name": "interface"},
    ]
