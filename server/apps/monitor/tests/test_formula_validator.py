import pytest

from apps.monitor.expression.errors import FormulaValidationError
from apps.monitor.expression.validators import validate_formula_condition


def formula(**overrides):
    data = {
        "type": "formula",
        "result_name": "错误率",
        "expression": "a / b * 100",
        "queries": [
            {
                "ref": "a",
                "metric_id": 1,
                "filter": [],
                "group_algorithm": "sum",
                "group_by": ["instance_id", "status"],
            },
            {
                "ref": "b",
                "metric_id": 2,
                "filter": [],
                "group_algorithm": "sum",
                "group_by": ["instance_id"],
            },
        ],
    }
    data.update(overrides)
    return data


def test_validate_formula_allows_subset_dimensions():
    result = validate_formula_condition(formula())

    assert result.anchor_ref == "a"
    assert result.warnings == []


def test_validate_formula_warns_cross_dimension_reuse():
    payload = formula(
        expression="a / b - c",
        queries=[
            {
                "ref": "a",
                "metric_id": 1,
                "filter": [],
                "group_algorithm": "sum",
                "group_by": ["instance_id", "status"],
            },
            {
                "ref": "b",
                "metric_id": 2,
                "filter": [],
                "group_algorithm": "sum",
                "group_by": ["instance_id"],
            },
            {
                "ref": "c",
                "metric_id": 3,
                "filter": [],
                "group_algorithm": "avg",
                "group_by": ["status"],
            },
        ],
    )

    result = validate_formula_condition(payload)

    assert result.anchor_ref == "a"
    assert result.warnings
    assert "跨缺失维度复用" in result.warnings[0]["message"]


def test_validate_formula_rejects_extra_non_anchor_dimension():
    payload = formula(
        queries=[
            {
                "ref": "a",
                "metric_id": 1,
                "filter": [],
                "group_algorithm": "sum",
                "group_by": ["instance_id", "path"],
            },
            {
                "ref": "b",
                "metric_id": 2,
                "filter": [],
                "group_algorithm": "sum",
                "group_by": ["instance_id", "method"],
            },
        ],
    )

    with pytest.raises(FormulaValidationError) as exc:
        validate_formula_condition(payload)

    assert "锚点外额外维度" in str(exc.value)


def test_validate_formula_rejects_missing_variable_reference():
    payload = formula(expression="a / c")

    with pytest.raises(FormulaValidationError) as exc:
        validate_formula_condition(payload)

    assert "不存在" in str(exc.value)
