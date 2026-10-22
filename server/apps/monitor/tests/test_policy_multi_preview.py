"""多指标预览：每个条件独立查询、阈值和单位，维度复用警告沿用公式文案。"""

import logging

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models.monitor_metrics import Metric, MetricGroup
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.services.policy_preview import PolicyPreviewService

pytestmark = pytest.mark.django_db


def _metrics():
    obj = MonitorObject.objects.create(name="MultiPreviewObj", level="base", instance_id_keys=["instance_id"])
    plugin = MonitorPlugin.objects.create(name="MultiPreviewPlugin")
    group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
    cpu = Metric.objects.create(
        monitor_object=obj,
        monitor_plugin=plugin,
        metric_group=group,
        name="cpu_usage",
        display_name="CPU 使用率",
        query="cpu_usage{__$labels__}",
        instance_id_keys=["instance_id"],
        unit="percent",
    )
    memory = Metric.objects.create(
        monitor_object=obj,
        monitor_plugin=plugin,
        metric_group=group,
        name="mem_used",
        display_name="内存使用量",
        query="mem_used{__$labels__}",
        instance_id_keys=["instance_id"],
        unit="bytes",
    )
    return cpu, memory


def _condition(metric, ref, **overrides):
    data = {
        "ref": ref,
        "metric_id": metric.id,
        "filter": [],
        "group_algorithm": "avg",
        "group_by": ["instance_id"],
        "algorithm": "avg_over_time",
        "metric_unit": "percent",
        "calculation_unit": "percent",
        "threshold_unit": "percent",
        "role": "level",
        "threshold": [{"level": "warning", "method": ">", "value": 80}],
    }
    data.update(overrides)
    return data


def _payload(cpu, memory, **query_overrides):
    memory_condition = _condition(
        memory,
        "b",
        metric_unit="bytes",
        calculation_unit="gibibytes",
        threshold_unit="gibibytes",
        threshold=[{"level": "critical", "method": ">", "value": 0.5}],
    )
    memory_condition.update(query_overrides)
    return {
        "query_condition": {
            "type": "multi",
            "result_name": "CPU 与内存双高",
            "combinator": "all",
            "queries": [
                _condition(cpu, "a", group_by=["instance_id", "device"]),
                memory_condition,
            ],
        },
        "period": {"type": "min", "value": 5},
        "preview": {"duration_points": 1, "instance_id_values": ["h1"]},
    }


def test_preview_returns_one_card_per_condition(mocker):
    cpu, memory = _metrics()
    api = mocker.patch("apps.monitor.services.policy_preview.VictoriaMetricsAPI")
    api.return_value.query_range.side_effect = [
        {"status": "success", "data": {"result": [{"metric": {"instance_id": "h1"}, "values": [[1, "90"]]}]}},
        {
            "status": "success",
            "data": {"result": [{"metric": {"instance_id": "h1"}, "values": [[1, str(1024**3)]]}]},
        },
    ]
    out = PolicyPreviewService(_payload(cpu, memory)).preview()
    assert api.return_value.query_range.call_count == 2
    assert len(out["conditions"]) == 2
    cpu_card, memory_card = out["conditions"]
    assert "cpu_usage" in cpu_card["query"]
    assert "mem_used" not in cpu_card["query"]
    assert 'instance_id=~"h1"' in cpu_card["query"]
    assert "mem_used" in memory_card["query"]
    assert "cpu_usage" not in memory_card["query"]
    assert cpu_card["metric_name"] == "CPU 使用率"
    assert cpu_card["threshold"] == [{"level": "warning", "method": ">", "value": 80}]
    assert cpu_card["chart_unit"] == "percent"
    assert memory_card["threshold"] == [{"level": "critical", "method": ">", "value": 0.5}]
    assert memory_card["chart_unit"] == "gibibytes"
    assert memory_card["data"]["data"]["result"][0]["values"][0][1] == "1.0"
    assert out["warnings"] == [
        {
            "code": "MULTI_DIMENSION_REUSE",
            "message": "指标 b 将按 instance_id 对齐，并跨缺失维度复用数据",
        }
    ]
    assert out["overlay"] is False
    assert out["query"] == cpu_card["query"]
    assert out["threshold"] == cpu_card["threshold"]


def test_preview_vm_error_raises_without_logging_response_body(mocker, caplog):
    cpu, memory = _metrics()
    body = "vm-result-body-not-logged"
    api = mocker.patch("apps.monitor.services.policy_preview.VictoriaMetricsAPI")
    api.return_value.query_range.return_value = {
        "status": "error",
        "error": "upstream failed",
        "data": {"result": [{"secret": body}]},
    }
    caplog.set_level(logging.DEBUG, logger="monitor")
    with pytest.raises(BaseAppException, match="upstream failed"):
        PolicyPreviewService(_payload(cpu, memory, group_by=["instance_id"])).preview()
    text = "\n".join(record.getMessage() for record in caplog.records)
    assert body not in text
    assert not [record for record in caplog.records if record.levelno == logging.INFO]


def _formula_preview_payload(cpu, memory):
    return {
        "query_condition": {
            "type": "multi",
            "result_name": "错误率与请求数",
            "combinator": "all",
            "queries": [
                {
                    "ref": "a",
                    "source": "formula",
                    "metric_name": "错误率",
                    "expression": "a1 / a2 * 100",
                    "operands": [
                        {
                            "ref": "a1",
                            "metric_id": cpu.id,
                            "filter": [],
                            "group_algorithm": "sum",
                            "group_by": ["instance_id"],
                        },
                        {
                            "ref": "a2",
                            "metric_id": memory.id,
                            "filter": [],
                            "group_algorithm": "sum",
                            "group_by": ["instance_id"],
                        },
                    ],
                    "group_by": ["instance_id"],
                    "algorithm": "avg_over_time",
                    "metric_unit": "",
                    "calculation_unit": "percent",
                    "threshold_unit": "percent",
                    "role": "level",
                    "threshold": [{"level": "warning", "method": ">", "value": 5}],
                },
                _condition(
                    memory,
                    "b",
                    role="gate",
                    metric_unit="bytes",
                    calculation_unit="bytes",
                    threshold_unit="bytes",
                    threshold=[{"method": ">", "value": 100}],
                ),
            ],
        },
        "period": {"type": "min", "value": 5},
        "preview": {"duration_points": 1, "instance_id_values": ["h1"]},
    }


def test_preview_formula_condition_uses_result_name(mocker):
    cpu, memory = _metrics()
    api = mocker.patch("apps.monitor.services.policy_preview.VictoriaMetricsAPI")
    api.return_value.query_range.side_effect = [
        {"status": "success", "data": {"result": [{"metric": {"instance_id": "h1"}, "values": [[1, "12"]]}]}},
        {"status": "success", "data": {"result": [{"metric": {"instance_id": "h1"}, "values": [[1, "300"]]}]}},
    ]
    out = PolicyPreviewService(_formula_preview_payload(cpu, memory)).preview()
    assert api.return_value.query_range.call_count == 2
    formula_card, gate_card = out["conditions"]
    assert formula_card["metric_name"] == "错误率"
    assert formula_card["ref"] == "a"
    assert "cpu_usage" in formula_card["query"]
    assert "mem_used" in formula_card["query"]
    assert formula_card["query"].count('instance_id=~"h1"') >= 2
    assert "cpu_usage" not in gate_card["query"]
    assert gate_card["metric_name"] == "内存使用量"


def test_preview_formula_vm_error_does_not_log_response_body(mocker, caplog):
    cpu, memory = _metrics()
    body = "formula-vm-body-not-logged"
    api = mocker.patch("apps.monitor.services.policy_preview.VictoriaMetricsAPI")
    api.return_value.query_range.return_value = {
        "status": "error",
        "error": "upstream failed",
        "data": {"result": [{"secret": body}]},
    }
    caplog.set_level(logging.DEBUG, logger="monitor")
    with pytest.raises(BaseAppException, match="upstream failed"):
        PolicyPreviewService(_formula_preview_payload(cpu, memory)).preview()
    text = "\n".join(record.getMessage() for record in caplog.records)
    assert body not in text
