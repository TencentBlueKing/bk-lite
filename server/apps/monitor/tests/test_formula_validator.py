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


def test_validate_formula_rejects_invalid_filter_label_name():
    payload = formula(
        queries=[
            {
                "ref": "a",
                "metric_id": 1,
                "filter": [{"name": 'bad"label', "method": "=", "value": "api"}],
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
        ]
    )

    with pytest.raises(FormulaValidationError) as exc:
        validate_formula_condition(payload)

    assert "非法字符" in str(exc.value)


def test_validate_formula_rejects_filter_item_not_object():
    payload = formula(
        queries=[
            {
                "ref": "a",
                "metric_id": 1,
                "filter": [1],
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
        ]
    )

    with pytest.raises(FormulaValidationError) as exc:
        validate_formula_condition(payload)

    assert "filter" in str(exc.value)


def test_validate_formula_rejects_empty_filter_object():
    payload = formula(
        queries=[
            {
                "ref": "a",
                "metric_id": 1,
                "filter": [{}],
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
        ]
    )

    with pytest.raises(FormulaValidationError) as exc:
        validate_formula_condition(payload)

    assert "filter" in str(exc.value)


def test_validate_formula_rejects_query_item_not_object():
    payload = formula(
        queries=[
            1,
            {
                "ref": "b",
                "metric_id": 2,
                "group_algorithm": "sum",
                "group_by": ["instance_id"],
            },
        ]
    )

    with pytest.raises(FormulaValidationError) as exc:
        validate_formula_condition(payload)

    assert "必须是对象" in str(exc.value)


@pytest.mark.parametrize("bad_group_by", [["instance_id", 1], ["instance_id", ""]])
def test_validate_formula_rejects_invalid_group_by_item(bad_group_by):
    payload = formula(
        queries=[
            {
                "ref": "a",
                "metric_id": 1,
                "filter": [],
                "group_algorithm": "sum",
                "group_by": bad_group_by,
            },
            {
                "ref": "b",
                "metric_id": 2,
                "filter": [],
                "group_algorithm": "sum",
                "group_by": ["instance_id"],
            },
        ]
    )

    with pytest.raises(FormulaValidationError) as exc:
        validate_formula_condition(payload)

    assert "group_by" in str(exc.value)


def test_validate_formula_rejects_expression_with_single_distinct_variable():
    payload = formula(expression="a * 100")

    with pytest.raises(FormulaValidationError) as exc:
        validate_formula_condition(payload)

    assert "至少引用两个指标变量" in str(exc.value)


def test_validate_formula_rejects_unused_query_variable():
    payload = formula(
        expression="a / b",
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
                "group_algorithm": "sum",
                "group_by": ["instance_id"],
            },
        ],
    )

    with pytest.raises(FormulaValidationError) as exc:
        validate_formula_condition(payload)

    assert "未被表达式引用" in str(exc.value)


def test_validate_formula_rejects_invalid_group_algorithm():
    payload = formula(
        queries=[
            {
                "ref": "a",
                "metric_id": 1,
                "filter": [],
                "group_algorithm": "median",
                "group_by": ["instance_id", "status"],
            },
            {
                "ref": "b",
                "metric_id": 2,
                "filter": [],
                "group_algorithm": "sum",
                "group_by": ["instance_id"],
            },
        ]
    )

    with pytest.raises(FormulaValidationError) as exc:
        validate_formula_condition(payload)

    assert "group_algorithm" in str(exc.value)
