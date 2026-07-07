import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.expression.compiler import FormulaCompiler
from apps.monitor.expression.query import build_formula_query


class MetricObj:
    def __init__(self, metric_id, query, unit="", display_name=""):
        self.id = metric_id
        self.query = query
        self.unit = unit
        self.display_name = display_name
        self.dimensions = []


def test_compile_formula_with_group_left():
    metrics = {
        1: MetricObj(1, "disk_read_latency_gauge{__$labels__}"),
        2: MetricObj(2, "disk_total_gauge{__$labels__}"),
    }
    condition = {
        "type": "formula",
        "result_name": "读延迟占比",
        "expression": "a / b",
        "queries": [
            {
                "ref": "a",
                "metric_id": 1,
                "filter": [],
                "group_algorithm": "avg",
                "group_by": ["instance_id", "config_type"],
            },
            {"ref": "b", "metric_id": 2, "filter": [], "group_algorithm": "avg", "group_by": ["instance_id"]},
        ],
    }

    compiled = FormulaCompiler(condition, metrics).compile()

    assert "avg(disk_read_latency_gauge{}) by (instance_id,config_type)" in compiled.query
    assert "/ on(instance_id) group_left" in compiled.query
    assert "avg(disk_total_gauge{}) by (instance_id)" in compiled.query
    assert compiled.result_name == "读延迟占比"
    assert compiled.group_by == ["instance_id", "config_type"]


def test_compile_formula_same_dimensions_without_group_left():
    metrics = {
        1: MetricObj(1, "a_metric{__$labels__}"),
        2: MetricObj(2, "b_metric{__$labels__}"),
    }
    condition = {
        "type": "formula",
        "result_name": "比率",
        "expression": "a / b * 100",
        "queries": [
            {"ref": "a", "metric_id": 1, "filter": [], "group_algorithm": "sum", "group_by": ["instance_id"]},
            {"ref": "b", "metric_id": 2, "filter": [], "group_algorithm": "sum", "group_by": ["instance_id"]},
        ],
    }

    compiled = FormulaCompiler(condition, metrics).compile()

    assert "group_left" not in compiled.query
    assert "* 100" in compiled.query


def test_compile_nested_formula_with_group_right():
    metrics = {
        1: MetricObj(1, "request_count{__$labels__}"),
        2: MetricObj(2, "request_total{__$labels__}"),
    }
    condition = {
        "type": "formula",
        "result_name": "请求占比",
        "expression": "a + (b / a)",
        "queries": [
            {
                "ref": "a",
                "metric_id": 1,
                "filter": [],
                "group_algorithm": "sum",
                "group_by": ["instance_id", "status"],
            },
            {"ref": "b", "metric_id": 2, "filter": [], "group_algorithm": "sum", "group_by": ["instance_id"]},
        ],
    }

    compiled = FormulaCompiler(condition, metrics).compile()

    assert "/ on(instance_id) group_right" in compiled.query
    assert compiled.group_by == ["instance_id", "status"]


def test_build_formula_query_rejects_invalid_query_shape_with_controlled_error():
    condition = {
        "type": "formula",
        "result_name": "x",
        "expression": "a/b",
        "queries": [1],
    }

    with pytest.raises(BaseAppException):
        build_formula_query(condition)
