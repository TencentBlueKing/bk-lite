import pytest
from django.core.management import call_command
from io import StringIO

from apps.monitor.models import MonitorObject
from apps.monitor.models.monitor_metrics import Metric, MetricGroup
from apps.monitor.models.plugin import MonitorPlugin


@pytest.fixture
def obj_with_seed(db):
    obj = MonitorObject.objects.create(
        name="Mysql", level="base",
        display_fields=[{"name": "old", "sort_order": 0, "metrics": [{"plugin": "Mysql", "metric": "mysql_uptime"}]}],
        display_fields_customized=True,
    )
    plugin = MonitorPlugin.objects.create(name="Mysql")
    plugin.monitor_object.add(obj)
    grp = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
    for m in ["mysql_connection_utilization", "mysql_queries_rate"]:
        Metric.objects.create(monitor_object=obj, monitor_plugin=plugin, metric_group=grp,
                              name=m, display_name=m, query="x{__$labels__}", data_type="Number")
    return obj


@pytest.mark.django_db
def test_apply_rewrites_and_clears_customized(obj_with_seed):
    call_command("refresh_display_fields", "--apply", stdout=StringIO())
    obj_with_seed.refresh_from_db()
    names = [c["name"] for c in obj_with_seed.display_fields]
    assert "连接使用率" in names  # 来自 mysql metrics.json 新种子
    assert obj_with_seed.display_fields_customized is False


@pytest.mark.django_db
def test_dry_run_does_not_write(obj_with_seed):
    call_command("refresh_display_fields", stdout=StringIO())
    obj_with_seed.refresh_from_db()
    assert obj_with_seed.display_fields[0]["name"] == "old"
    assert obj_with_seed.display_fields_customized is True
