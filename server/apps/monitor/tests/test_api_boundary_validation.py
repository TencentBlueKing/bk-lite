"""API 边界测试 - 对应测试方案 A-01..A-07。

构造非法 payload,验证 MonitorPolicySerializer 在 API 边界拒绝。
A-05 文档期望 expression="b / a" 被拒,但 76ba4c155 已放宽首变量必须首行的校验,
所以 A-05 现在被接受(行为符合代码现状),与文档期望冲突——需更新测试方案文档。
"""
import pytest
from rest_framework import serializers

from apps.monitor.models.monitor_metrics import Metric, MetricGroup
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.serializers.monitor_policy import MonitorPolicySerializer

pytestmark = pytest.mark.django_db


@pytest.fixture
def obj_and_metric():
    obj = MonitorObject.objects.create(
        name="APIBObj", level="base", instance_id_keys=["instance_id", "status"]
    )
    plugin = MonitorPlugin.objects.create(name="APIBPlugin")
    mg = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
    m = Metric.objects.create(
        monitor_object=obj, monitor_plugin=plugin, metric_group=mg, name="m1",
        query="x{__$labels__}", instance_id_keys=["instance_id", "status"],
        dimensions=[{"name": "instance_id"}, {"name": "status"}]
    )
    return obj, m


def _payload(qc, group_by, obj, source=None):
    return {
        "name": "p",
        "alert_name": "alert",
        "monitor_object": obj.id,
        "query_condition": qc,
        "group_by": group_by,
        "source": source or {"type": "instance", "values": [1]},
        "period": {"type": "min", "value": 5},
        "algorithm": "avg_over_time",
        "group_algorithm": "avg",
    }


class TestAPIBoundary:
    def test_A01_metric_group_by_injection_rejected(self, obj_and_metric):
        obj, m = obj_and_metric
        qc = {"type": "metric", "metric_id": m.id, "filter": []}
        s = MonitorPolicySerializer(data=_payload(qc, ["instance_id", "x) or vector(1"], obj))
        assert not s.is_valid()
        assert "group_by" in s.errors

    def test_A02_metric_filter_value_array_rejected(self, obj_and_metric):
        obj, m = obj_and_metric
        qc = {"type": "metric", "metric_id": m.id, "filter": [
            {"name": "instance_id", "method": "=", "value": ["checkout"]}
        ]}
        s = MonitorPolicySerializer(data=_payload(qc, ["instance_id"], obj))
        assert not s.is_valid()
        # 错误在 query_condition 上
        assert "query_condition" in s.errors

    def test_A03_formula_group_by_injection_rejected(self, obj_and_metric):
        obj, m = obj_and_metric
        qc = {
            "type": "formula", "result_name": "x", "expression": "a / b",
            "queries": [
                {"ref": "a", "metric_id": m.id, "filter": [], "group_algorithm": "avg",
                 "group_by": ["instance_id", "x) or vector(1"]},
                {"ref": "b", "metric_id": m.id, "filter": [], "group_algorithm": "avg",
                 "group_by": ["instance_id"]},
            ],
        }
        s = MonitorPolicySerializer(data=_payload(qc, ["instance_id"], obj))
        assert not s.is_valid()
        assert "query_condition" in s.errors

    def test_A04_formula_unknown_metric_id_rejected(self, obj_and_metric):
        obj, m = obj_and_metric
        qc = {
            "type": "formula", "result_name": "x", "expression": "a / b",
            "queries": [
                {"ref": "a", "metric_id": m.id, "filter": [], "group_algorithm": "avg", "group_by": ["instance_id"]},
                {"ref": "b", "metric_id": 999999, "filter": [], "group_algorithm": "avg", "group_by": ["instance_id"]},
            ],
        }
        s = MonitorPolicySerializer(data=_payload(qc, ["instance_id"], obj))
        assert not s.is_valid()
        assert "query_condition" in s.errors

    def test_A05_formula_b_over_a_now_accepted_per_76ba4c155(self, obj_and_metric):
        """A-05 文档期望:expression='b / a' 被拒。

        实际: 76ba4c155 放宽了「首变量必须首行」校验,b / a 现被接受(anchor=首个query=a)。
        与测试方案文档期望冲突,这里断言实际行为(通过),并在报告里标注需更新文档。
        """
        obj, m = obj_and_metric
        qc = {
            "type": "formula", "result_name": "x", "expression": "b / a",
            "queries": [
                {"ref": "a", "metric_id": m.id, "filter": [], "group_algorithm": "avg",
                 "group_by": ["instance_id", "status"]},
                {"ref": "b", "metric_id": m.id, "filter": [], "group_algorithm": "avg",
                 "group_by": ["instance_id"]},
            ],
        }
        s = MonitorPolicySerializer(data=_payload(qc, ["instance_id", "status"], obj))
        assert s.is_valid(), s.errors

    def test_A06_formula_anchor_missing_instance_id_rejected(self, obj_and_metric):
        obj, m = obj_and_metric
        qc = {
            "type": "formula", "result_name": "x", "expression": "a / b",
            "queries": [
                {"ref": "a", "metric_id": m.id, "filter": [], "group_algorithm": "avg", "group_by": ["status"]},
                {"ref": "b", "metric_id": m.id, "filter": [], "group_algorithm": "avg", "group_by": ["status"]},
            ],
        }
        s = MonitorPolicySerializer(data=_payload(qc, ["status"], obj))
        assert not s.is_valid()
        assert "query_condition" in s.errors

    def test_A07_formula_non_anchor_extra_dimension_rejected(self, obj_and_metric):
        obj, m = obj_and_metric
        qc = {
            "type": "formula", "result_name": "x", "expression": "a / b",
            "queries": [
                {"ref": "a", "metric_id": m.id, "filter": [], "group_algorithm": "avg",
                 "group_by": ["instance_id", "path"]},
                {"ref": "b", "metric_id": m.id, "filter": [], "group_algorithm": "avg",
                 "group_by": ["instance_id", "method"]},
            ],
        }
        s = MonitorPolicySerializer(data=_payload(qc, ["instance_id", "path"], obj))
        assert not s.is_valid()
        assert "query_condition" in s.errors
