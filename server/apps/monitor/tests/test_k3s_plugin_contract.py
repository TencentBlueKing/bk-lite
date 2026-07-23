import json
from pathlib import Path

import pytest
import yaml


PLUGIN_DIR = (
    Path(__file__).resolve().parents[1]
    / "support-files"
    / "plugins"
    / "unknown"
    / "k3s"
    / "k3s"
)
EXPECTED_OBJECTS = {
    "K3SCluster": ("base", ["instance_id"], 4),
    "K3SNode": ("derivative", ["instance_id", "node"], 28),
    "K3SPod": ("derivative", ["instance_id", "pod"], 8),
}


def _load_plugin():
    return json.loads((PLUGIN_DIR / "metrics.json").read_text(encoding="utf-8"))


def test_k3s_plugin_has_independent_objects_and_identity():
    plugin = _load_plugin()

    assert plugin["plugin"] == "K3S"
    assert "instance_type='k3s'" in plugin["status_query"]
    assert "instance_type='k8s'" not in plugin["status_query"]

    objects = {item["name"]: item for item in plugin["objects"]}
    assert set(objects) == set(EXPECTED_OBJECTS)

    for name, (level, instance_id_keys, metric_count) in EXPECTED_OBJECTS.items():
        monitor_object = objects[name]
        assert monitor_object["type"] == "K3S"
        assert monitor_object["level"] == level
        assert monitor_object["instance_id_keys"] == instance_id_keys
        assert len(monitor_object["metrics"]) == metric_count


def test_k3s_plugin_queries_and_metric_references_are_self_contained():
    plugin = _load_plugin()

    for monitor_object in plugin["objects"]:
        metric_names = {metric["name"] for metric in monitor_object["metrics"]}
        assert set(monitor_object["supplementary_indicators"]) <= metric_names

        display_metric_names = {
            metric_ref["metric"]
            for display_field in monitor_object["display_fields"]
            for metric_ref in display_field["metrics"]
        }
        assert display_metric_names <= metric_names

        queries = [monitor_object["default_metric"]]
        queries.extend(metric["query"] for metric in monitor_object["metrics"])
        for query in queries:
            assert 'instance_type="k3s"' in query or "instance_type='k3s'" in query
            assert 'instance_type="k8s"' not in query
            assert "instance_type='k8s'" not in query

        serialized = json.dumps(monitor_object, ensure_ascii=False)
        assert '"plugin": "K8S"' not in serialized


def test_k3s_plugin_has_independent_localized_copy():
    for locale in ("zh-Hans", "en"):
        translations = yaml.safe_load(
            (PLUGIN_DIR / "language" / f"{locale}.yaml").read_text(encoding="utf-8")
        )
        serialized = json.dumps(translations, ensure_ascii=False)
        assert "K3S" in serialized
        assert "K8S" not in serialized


@pytest.mark.django_db
def test_k3s_plugin_import_is_idempotent_and_coexists_with_k8s():
    from apps.monitor.management.services.plugin_migrate import (
        _import_plugins_from_files,
    )
    from apps.monitor.models import Metric, MonitorObject
    from apps.monitor.models.plugin import MonitorPlugin

    for name in ("Cluster", "Node", "Pod"):
        MonitorObject.objects.create(name=name, level="base")

    plugin_path = str(PLUGIN_DIR / "metrics.json")
    assert _import_plugins_from_files([plugin_path])[:2] == (1, 0)
    assert _import_plugins_from_files([plugin_path])[:2] == (1, 0)

    assert MonitorPlugin.objects.filter(name="K3S").count() == 1
    assert set(
        MonitorObject.objects.filter(name__in=EXPECTED_OBJECTS).values_list(
            "name", flat=True
        )
    ) == set(EXPECTED_OBJECTS)
    assert set(
        MonitorObject.objects.filter(name__in={"Cluster", "Node", "Pod"}).values_list(
            "name", flat=True
        )
    ) == {"Cluster", "Node", "Pod"}
    assert Metric.objects.filter(monitor_plugin__name="K3S").count() == 40
