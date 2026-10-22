"""Issue 6485: 仍被指标引用的分组不能改所属对象或插件。"""

import apps.node_mgmt  # noqa: F401  INSTALL_APPS 需含 node_mgmt（monitor.apps.ready → nats.monitor）
import pytest

from apps.monitor.models.monitor_metrics import Metric, MetricGroup
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.serializers.monitor_metrics import MetricGroupSerializer, MetricSerializer

pytestmark = pytest.mark.django_db

SCOPE_LOCKED_MESSAGE = "仍被指标引用"


def _object(name):
    return MonitorObject.objects.create(name=name, level="base", instance_id_keys=["instance_id"])


def _plugin(name):
    return MonitorPlugin.objects.create(name=name)


def _group(obj, plugin, name="cpu", description="origin"):
    return MetricGroup.objects.create(
        monitor_object=obj,
        monitor_plugin=plugin,
        name=name,
        description=description,
    )


def _metric(obj, plugin, group, name="cpu_usage"):
    return Metric.objects.create(
        monitor_object=obj,
        monitor_plugin=plugin,
        metric_group=group,
        name=name,
        instance_id_keys=["instance_id"],
        description="before",
    )


def _partial(instance, data):
    return MetricGroupSerializer(instance=instance, data=data, partial=True)


def test_referenced_group_object_move_is_rejected_and_metric_description_still_saves():
    obj_a = _object("Issue6485ObjA")
    obj_b = _object("Issue6485ObjB")
    plugin = _plugin("Issue6485PluginA")
    group = _group(obj_a, plugin)
    metric = _metric(obj_a, plugin, group)

    serializer = _partial(group, {"monitor_object": obj_b.id})
    if serializer.is_valid():
        serializer.save()
        group.refresh_from_db()
        metric.refresh_from_db()
        description = MetricSerializer(instance=metric, data={"description": "only-desc"}, partial=True)
        raise AssertionError(
            "referenced group object move was saved; "
            f"group_object={group.monitor_object_id} "
            f"metric_object={metric.monitor_object_id} "
            f"description_update_valid={description.is_valid()} "
            f"description_errors={description.errors}"
        )

    assert "monitor_object" in serializer.errors
    assert "monitor_plugin" not in serializer.errors
    assert SCOPE_LOCKED_MESSAGE in str(serializer.errors["monitor_object"])
    group.refresh_from_db()
    metric.refresh_from_db()
    assert group.monitor_object_id == obj_a.id
    assert metric.monitor_object_id == obj_a.id
    assert metric.monitor_plugin_id == plugin.id

    description = MetricSerializer(instance=metric, data={"description": "only-desc"}, partial=True)
    assert description.is_valid(), description.errors
    description.save()
    metric.refresh_from_db()
    group.refresh_from_db()
    assert metric.description == "only-desc"
    assert metric.monitor_object_id == obj_a.id
    assert group.monitor_object_id == obj_a.id


def test_referenced_group_plugin_move_is_rejected_and_rows_stay():
    obj = _object("Issue6485ObjPlugin")
    plugin_a = _plugin("Issue6485PluginP1")
    plugin_b = _plugin("Issue6485PluginP2")
    group = _group(obj, plugin_a, name="mem")
    metric = _metric(obj, plugin_a, group, name="mem_usage")

    serializer = _partial(group, {"monitor_plugin": plugin_b.id})
    assert not serializer.is_valid()
    assert "monitor_plugin" in serializer.errors
    assert "monitor_object" not in serializer.errors
    assert SCOPE_LOCKED_MESSAGE in str(serializer.errors["monitor_plugin"])

    group.refresh_from_db()
    metric.refresh_from_db()
    assert group.monitor_plugin_id == plugin_a.id
    assert group.monitor_object_id == obj.id
    assert metric.monitor_plugin_id == plugin_a.id
    assert metric.monitor_object_id == obj.id
    assert metric.metric_group_id == group.id


def test_referenced_group_rejects_only_changed_scope_fields():
    obj_a = _object("Issue6485BothA")
    obj_b = _object("Issue6485BothB")
    plugin_a = _plugin("Issue6485BothP1")
    plugin_b = _plugin("Issue6485BothP2")
    group = _group(obj_a, plugin_a, name="both", description="keep")
    metric = _metric(obj_a, plugin_a, group, name="both_metric")

    serializer = _partial(
        group,
        {"monitor_object": obj_b.id, "monitor_plugin": plugin_b.id, "description": "should-not-save"},
    )
    assert not serializer.is_valid()
    assert set(serializer.errors) == {"monitor_object", "monitor_plugin"}
    assert SCOPE_LOCKED_MESSAGE in str(serializer.errors["monitor_object"])
    assert SCOPE_LOCKED_MESSAGE in str(serializer.errors["monitor_plugin"])

    group.refresh_from_db()
    metric.refresh_from_db()
    assert group.monitor_object_id == obj_a.id
    assert group.monitor_plugin_id == plugin_a.id
    assert group.description == "keep"
    assert metric.monitor_object_id == obj_a.id
    assert metric.monitor_plugin_id == plugin_a.id


def test_unreferenced_group_can_change_object():
    obj_a = _object("Issue6485EmptyA")
    obj_b = _object("Issue6485EmptyB")
    plugin = _plugin("Issue6485EmptyPlugin")
    group = _group(obj_a, plugin, name="disk")

    serializer = _partial(group, {"monitor_object": obj_b.id})
    assert serializer.is_valid(), serializer.errors
    serializer.save()
    group.refresh_from_db()
    assert group.monitor_object_id == obj_b.id
    assert group.monitor_plugin_id == plugin.id
    assert not Metric.objects.filter(metric_group_id=group.id).exists()


def test_referenced_group_name_and_description_still_update():
    obj = _object("Issue6485NameObj")
    plugin = _plugin("Issue6485NamePlugin")
    group = _group(obj, plugin, name="net", description="old")
    metric = _metric(obj, plugin, group, name="net_in")

    serializer = _partial(
        group,
        {
            "monitor_object": obj.id,
            "monitor_plugin": plugin.id,
            "name": "net-renamed",
            "description": "new-desc",
        },
    )
    assert serializer.is_valid(), serializer.errors
    serializer.save()
    group.refresh_from_db()
    metric.refresh_from_db()
    assert group.name == "net-renamed"
    assert group.description == "new-desc"
    assert group.monitor_object_id == obj.id
    assert group.monitor_plugin_id == plugin.id
    assert metric.monitor_object_id == obj.id
    assert metric.monitor_plugin_id == plugin.id
    assert metric.description == "before"
