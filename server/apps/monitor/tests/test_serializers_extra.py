"""monitor 序列化器校验规格测试。"""

import pytest

from rest_framework import serializers

from apps.monitor.models.monitor_metrics import Metric, MetricGroup
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.serializers.monitor_metrics import MetricGroupSerializer, MetricSerializer
from apps.monitor.serializers.monitor_policy import MonitorPolicySerializer

pytestmark = pytest.mark.django_db


class TestMonitorPolicyValidators:
    def _s(self, initial=None):
        s = MonitorPolicySerializer()
        if initial is not None:
            s.initial_data = initial
        return s

    def test_validate_threshold_empty_ok(self):
        assert self._s().validate_threshold([]) == []

    def test_validate_threshold_not_list(self):
        with pytest.raises(serializers.ValidationError):
            self._s().validate_threshold({"x": 1})

    def test_validate_threshold_bad_method(self):
        with pytest.raises(serializers.ValidationError):
            self._s().validate_threshold([{"method": "??", "value": 1, "level": "warning"}])

    def test_validate_threshold_missing_value(self):
        with pytest.raises(serializers.ValidationError):
            self._s().validate_threshold([{"method": ">", "level": "warning"}])

    def test_validate_threshold_bad_level(self):
        with pytest.raises(serializers.ValidationError):
            self._s().validate_threshold([{"method": ">", "value": 1, "level": "bogus"}])

    def test_validate_threshold_ok(self):
        val = [{"method": ">", "value": 80, "level": "critical"}]
        assert self._s().validate_threshold(val) == val

    def test_validate_query_condition_pmq_requires_query(self):
        with pytest.raises(serializers.ValidationError):
            self._s().validate_query_condition({"type": "pmq"})

    def test_validate_query_condition_pmq_ok(self):
        v = {"type": "pmq", "query": "up"}
        assert self._s().validate_query_condition(v) == v

    def test_validate_query_condition_metric_requires_id(self):
        with pytest.raises(serializers.ValidationError):
            self._s().validate_query_condition({"type": "metric"})

    def test_validate_query_condition_rejects_injection_name(self):
        with pytest.raises(serializers.ValidationError):
            self._s().validate_query_condition({
                "type": "metric", "metric_id": 1,
                "filter": [{"name": "bad name", "method": "=", "value": "x"}],
            })

    def test_validate_query_condition_rejects_bad_method(self):
        with pytest.raises(serializers.ValidationError):
            self._s().validate_query_condition({
                "type": "metric", "metric_id": 1,
                "filter": [{"name": "instance_id", "method": "LIKE", "value": "x"}],
            })

    def test_validate_query_condition_rejects_structured_filter_value(self):
        with pytest.raises(serializers.ValidationError) as exc:
            self._s().validate_query_condition(
                {
                    "type": "metric",
                    "metric_id": 1,
                    "filter": [{"name": "service", "method": "=", "value": ["checkout"]}],
                }
            )

        assert "必须是标量" in str(exc.value)

    def test_validate_source_requires_type_and_values(self):
        with pytest.raises(serializers.ValidationError):
            self._s().validate_source({"type": "instance"})

    def test_validate_source_bad_type(self):
        with pytest.raises(serializers.ValidationError):
            self._s().validate_source({"type": "bogus", "values": []})

    def test_validate_source_ok(self):
        v = {"type": "instance", "values": ["a"]}
        assert self._s().validate_source(v) == v

    def test_validate_algorithm_bad(self):
        with pytest.raises(serializers.ValidationError):
            self._s().validate_algorithm("bogus")

    def test_validate_group_by_autocorrects_primary_key(self):
        obj = MonitorObject.objects.create(name="SPGObj", level="base", instance_id_keys=["instance_id", "device"])
        s = self._s(initial={"monitor_object": obj.id})
        # group_by 首位不是主键 → 自动纠正到首位
        out = s.validate_group_by(["device", "instance_id"])
        assert out[0] == "instance_id"

    def test_validate_group_by_no_object_passthrough(self):
        s = self._s(initial={})
        assert s.validate_group_by(["x"]) == ["x"]

    def test_validate_group_by_rejects_invalid_label_name(self):
        with pytest.raises(serializers.ValidationError) as exc:
            self._s(initial={}).validate_group_by(["instance_id", "x) or vector(1"])

        assert "非法字符" in str(exc.value)


class TestMetricGroupSerializer:
    def test_rejects_duplicate_name(self):
        obj = MonitorObject.objects.create(name="MGSObj", level="base")
        plugin = MonitorPlugin.objects.create(name="MGSPlugin")
        MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="dup")
        s = MetricGroupSerializer(data={
            "monitor_object": obj.id, "monitor_plugin": plugin.id, "name": "dup",
        })
        # 同模板同名 → 唯一性校验拒绝（DRF UniqueTogether 或自定义 validate）
        assert not s.is_valid()
        assert s.errors

    def test_create_sets_is_pre_false(self):
        obj = MonitorObject.objects.create(name="MGSObj2", level="base")
        plugin = MonitorPlugin.objects.create(name="MGSPlugin2")
        s = MetricGroupSerializer(data={
            "monitor_object": obj.id, "monitor_plugin": plugin.id, "name": "g",
        })
        assert s.is_valid(), s.errors
        group = s.save()
        assert group.is_pre is False


class TestMetricSerializer:
    def test_requires_resolvable_instance_id_keys(self):
        obj = MonitorObject.objects.create(name="MSObj", level="base", instance_id_keys=[])
        plugin = MonitorPlugin.objects.create(name="MSPlugin")
        group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
        s = MetricSerializer(data={
            "monitor_object": obj.id, "monitor_plugin": plugin.id,
            "metric_group": group.id, "name": "m", "instance_id_keys": [],
        })
        assert not s.is_valid()
        assert "instance_id_keys" in s.errors

    def test_create_resolves_keys_and_is_pre_false(self):
        obj = MonitorObject.objects.create(name="MSObj2", level="base", instance_id_keys=["instance_id"])
        plugin = MonitorPlugin.objects.create(name="MSPlugin2")
        group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
        s = MetricSerializer(data={
            "monitor_object": obj.id, "monitor_plugin": plugin.id,
            "metric_group": group.id, "name": "m", "instance_id_keys": [],
        })
        assert s.is_valid(), s.errors
        metric = s.save()
        assert metric.instance_id_keys == ["instance_id"]
        assert metric.is_pre is False

    def test_to_representation_fills_keys(self):
        obj = MonitorObject.objects.create(name="MSObj3", level="base", instance_id_keys=["instance_id"])
        plugin = MonitorPlugin.objects.create(name="MSPlugin3")
        group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
        metric = Metric.objects.create(
            monitor_object=obj, monitor_plugin=plugin, metric_group=group, name="m", instance_id_keys=[],
        )
        data = MetricSerializer(metric).data
        assert data["instance_id_keys"] == ["instance_id"]
