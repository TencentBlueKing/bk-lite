import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models.monitor_metrics import Metric, MetricGroup
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.services.policy_preview import PolicyPreviewService


@pytest.mark.django_db
def test_preview_formula_uses_compiled_query(mocker):
    obj = MonitorObject.objects.create(name="FormulaObj", level="base")
    plugin = MonitorPlugin.objects.create(name="FormulaPlugin")
    group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
    a = Metric.objects.create(
        monitor_object=obj,
        monitor_plugin=plugin,
        metric_group=group,
        name="a_metric",
        query="a_metric{__$labels__}",
        instance_id_keys=["instance_id"],
    )
    b = Metric.objects.create(
        monitor_object=obj,
        monitor_plugin=plugin,
        metric_group=group,
        name="b_metric",
        query="b_metric{__$labels__}",
        instance_id_keys=["instance_id"],
    )
    captured = {}

    def fake_method(query, start, end, step, group_by, group_algorithm=None):
        captured["query"] = query
        captured["group_by"] = group_by
        return {"status": "success", "data": {"result": []}}

    mocker.patch.dict(
        "apps.monitor.services.policy_preview.METHOD",
        {"avg_over_time": fake_method},
        clear=False,
    )

    svc = PolicyPreviewService(
        {
            "query_condition": {
                "type": "formula",
                "result_name": "错误率",
                "expression": "a / b * 100",
                "queries": [
                    {
                        "ref": "a",
                        "metric_id": a.id,
                        "filter": [],
                        "group_algorithm": "sum",
                        "group_by": ["instance_id", "status"],
                    },
                    {
                        "ref": "b",
                        "metric_id": b.id,
                        "filter": [],
                        "group_algorithm": "sum",
                        "group_by": ["instance_id"],
                    },
                ],
            },
            "period": {"type": "min", "value": 5},
            "algorithm": "avg_over_time",
            "group_algorithm": "avg",
            "group_by": ["instance_id"],
            "preview": {"duration_points": 1},
        }
    )

    out = svc.preview()

    assert "on(instance_id) group_left" in captured["query"]
    assert captured["group_by"] == "instance_id,status"
    assert out["warnings"] == []


@pytest.mark.django_db
def test_preview_formula_returns_compiled_warnings(mocker):
    obj = MonitorObject.objects.create(name="FormulaWarningObj", level="base")
    plugin = MonitorPlugin.objects.create(name="FormulaWarningPlugin")
    group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
    a = Metric.objects.create(
        monitor_object=obj,
        monitor_plugin=plugin,
        metric_group=group,
        name="a_metric",
        query="a_metric{__$labels__}",
        instance_id_keys=["instance_id"],
    )
    b = Metric.objects.create(
        monitor_object=obj,
        monitor_plugin=plugin,
        metric_group=group,
        name="b_metric",
        query="b_metric{__$labels__}",
        instance_id_keys=["instance_id"],
    )

    mocker.patch.dict(
        "apps.monitor.services.policy_preview.METHOD",
        {"avg_over_time": lambda *args, **kwargs: {"status": "success", "data": {"result": []}}},
        clear=False,
    )

    svc = PolicyPreviewService(
        {
            "query_condition": {
                "type": "formula",
                "result_name": "错误率",
                "expression": "a / b",
                "queries": [
                    {
                        "ref": "a",
                        "metric_id": a.id,
                        "filter": [],
                        "group_algorithm": "sum",
                        "group_by": ["instance_id", "status"],
                    },
                    {
                        "ref": "b",
                        "metric_id": b.id,
                        "filter": [],
                        "group_algorithm": "sum",
                        "group_by": ["status"],
                    },
                ],
            },
            "period": {"type": "min", "value": 5},
            "algorithm": "avg_over_time",
            "group_algorithm": "avg",
            "group_by": ["instance_id"],
            "preview": {"duration_points": 1},
        }
    )

    out = svc.preview()

    assert out["warnings"] == [
        {
            "code": "FORMULA_DIMENSION_REUSE",
            "message": "指标 b 将按 status 对齐，并跨缺失维度复用数据",
        }
    ]


@pytest.mark.django_db
@pytest.mark.parametrize("bad_metric_id", ["abc", [1]])
def test_preview_formula_rejects_invalid_metric_id_with_controlled_error(bad_metric_id):
    svc = PolicyPreviewService(
        {
            "query_condition": {
                "type": "formula",
                "result_name": "错误率",
                "expression": "a / b",
                "queries": [
                    {
                        "ref": "a",
                        "metric_id": bad_metric_id,
                        "filter": [],
                        "group_algorithm": "sum",
                        "group_by": ["instance_id"],
                    },
                    {
                        "ref": "b",
                        "metric_id": 1,
                        "filter": [],
                        "group_algorithm": "sum",
                        "group_by": ["instance_id"],
                    },
                ],
            },
            "period": {"type": "min", "value": 5},
            "algorithm": "avg_over_time",
            "group_algorithm": "avg",
            "group_by": ["instance_id"],
            "preview": {"duration_points": 1},
        }
    )

    with pytest.raises(BaseAppException) as exc:
        svc.preview()

    assert "metric_id" in str(exc.value)
