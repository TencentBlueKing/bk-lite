import pytest

from apps.monitor.models import MonitorPlugin
from apps.monitor.models.monitor_metrics import Metric, MetricGroup
from apps.monitor.models.monitor_object import MonitorObject, MonitorObjectType
from apps.monitor.services.plugin import MonitorPluginService

pytestmark = pytest.mark.django_db


def test_compound_plugin_export_roundtrip_keeps_collect_type_and_status_query():
    object_type = MonitorObjectType.objects.create(id="CRType", name="CRType", order=1)
    plugin = MonitorPlugin.objects.create(
        name="CompoundRoundtrip",
        description="compound plugin",
        collector="Telegraf",
        collect_type="http",
        status_query="up{job='compound'}",
    )
    base = MonitorObject.objects.create(
        name="CRBase",
        level="base",
        type=object_type,
        instance_id_keys=["instance_id"],
    )
    child = MonitorObject.objects.create(
        name="CRChild",
        level="derivative",
        parent=base,
        type=object_type,
        instance_id_keys=["instance_id", "target"],
    )
    plugin.monitor_object.add(base, child)
    base_group = MetricGroup.objects.create(monitor_object=base, monitor_plugin=plugin, name="base-g")
    child_group = MetricGroup.objects.create(monitor_object=child, monitor_plugin=plugin, name="child-g")
    Metric.objects.create(
        monitor_object=base,
        monitor_plugin=plugin,
        metric_group=base_group,
        name="up",
        query="up{__$labels__}",
        instance_id_keys=["instance_id"],
    )
    Metric.objects.create(
        monitor_object=child,
        monitor_plugin=plugin,
        metric_group=child_group,
        name="child_up",
        query="child_up{__$labels__}",
        instance_id_keys=["instance_id", "target"],
    )

    exported = MonitorPluginService.export_monitor_plugin(plugin.id)

    assert exported["status_query"] == "up{job='compound'}"
    assert exported["collector"] == "Telegraf"
    assert exported["collect_type"] == "http"
    assert exported["is_compound_object"] is True
    assert {item["name"]: item["level"] for item in exported["objects"]} == {"CRBase": "base", "CRChild": "derivative"}

    MonitorPluginService.import_monitor_plugin(exported)
    plugin.refresh_from_db()
    assert plugin.collector == "Telegraf"
    assert plugin.collect_type == "http"
    assert plugin.status_query == "up{job='compound'}"
