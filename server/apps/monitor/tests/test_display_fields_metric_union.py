import pytest
from unittest.mock import patch

from apps.monitor.models.monitor_object import MonitorObject, MonitorInstance
from apps.monitor.models.monitor_metrics import Metric, MetricGroup
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.services.monitor_object import MonitorObjectService
from apps.monitor.utils.display_fields_metrics import extract_metric_names


def test_extract_metric_names_union_preserves_order_and_dedups():
    display_fields = [
        {"name": "CPU", "sort_order": 0, "metrics": [
            {"plugin": "A", "metric": "cpu"}, {"plugin": "B", "metric": "cpu_b"}]},
        {"name": "MEM", "sort_order": 1, "metrics": [
            {"plugin": "A", "metric": "mem"}, {"plugin": "A", "metric": "cpu"}]},
    ]
    assert extract_metric_names(display_fields) == ["cpu", "cpu_b", "mem"]


def test_extract_metric_names_empty():
    assert extract_metric_names([]) == []
    assert extract_metric_names(None) == []


@pytest.mark.django_db
@patch("apps.monitor.services.monitor_object.VictoriaMetricsAPI")
def test_get_monitor_instance_queries_display_fields_metrics(mock_vm):
    mock_vm.return_value.query.return_value = {"data": {"result": []}}
    obj = MonitorObject.objects.create(
        name="UTHostU", level="base",
        default_metric="any({instance_type='UTHostU'}) by (instance_id)",
        instance_id_keys=["instance_id"],
        supplementary_indicators=[],
        display_fields=[{"name": "CPU", "sort_order": 0,
                         "metrics": [{"plugin": "P", "metric": "cpu_usage_total"}]}],
    )
    plugin = MonitorPlugin.objects.create(name="P")
    group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="Base")
    Metric.objects.create(monitor_object=obj, monitor_plugin=plugin, metric_group=group,
                          name="cpu_usage_total", display_name="CPU", query="cpu_usage_total{__$labels__}",
                          unit="percent", data_type="Number", instance_id_keys=["instance_id"])
    MonitorInstance.objects.create(id="('i1',)", name="i1", monitor_object=obj)

    res = MonitorObjectService.get_monitor_instance(
        obj.id, page=1, page_size=10, name=None,
        qs=MonitorInstance.objects.all(), add_metrics=True,
    )
    queried = [c.args[0] for c in mock_vm.return_value.query.call_args_list]
    assert any("cpu_usage_total" in q for q in queried)
    assert res["count"] == 1
