import pytest

from apps.monitor.expression.errors import MultiValidationError
from apps.monitor.expression.validators import validate_multi_condition


def _condition(ref="a", **overrides):
    data = {
        "ref": ref,
        "metric_id": 1,
        "filter": [],
        "group_algorithm": "avg",
        "group_by": ["instance_id"],
        "algorithm": "avg_over_time",
        "role": "level",
        "threshold": [
            {"level": "critical", "method": ">", "value": 90},
            {"level": "warning", "method": ">", "value": 80},
        ],
    }
    data.update(overrides)
    return data


def multi_payload(**overrides):
    data = {
        "type": "multi",
        "result_name": "CPU 与内存双高",
        "combinator": "all",
        "queries": [
            _condition("a"),
            _condition(
                "b",
                metric_id=2,
                group_by=["instance_id"],
            ),
        ],
    }
    data.update(overrides)
    return data


def test_validate_multi_accepts_level_and_gate_with_subset_dimension():
    payload = multi_payload(
        queries=[
            _condition("a", group_by=["instance_id", "device"]),
            _condition("b", metric_id=2, group_by=["instance_id"]),
            _condition(
                "c",
                metric_id=3,
                role="gate",
                group_by=["instance_id"],
                threshold=[{"method": ">", "value": 600}],
            ),
        ]
    )

    result = validate_multi_condition(payload)

    assert result.anchor_ref == "a"
    assert result.warnings[0]["code"] == "MULTI_DIMENSION_REUSE"
    assert "跨缺失维度复用" in result.warnings[0]["message"]
    assert payload["queries"][0]["metric_id"] == 1


def test_validate_multi_rejects_one_and_six_conditions():
    with pytest.raises(MultiValidationError, match="2 到 5"):
        validate_multi_condition(multi_payload(queries=[_condition("a")]))

    queries = [_condition(ref, metric_id=index + 1) for index, ref in enumerate("abcdef")]
    with pytest.raises(MultiValidationError, match="2 到 5"):
        validate_multi_condition(multi_payload(queries=queries))


def test_validate_multi_rejects_all_gates_duplicate_ref_and_extra_dimension():
    with pytest.raises(MultiValidationError, match="参与级别"):
        validate_multi_condition(
            multi_payload(
                queries=[
                    _condition("a", role="gate", threshold=[{"method": ">", "value": 1}]),
                    _condition("b", role="gate", threshold=[{"method": ">", "value": 1}]),
                ]
            )
        )

    with pytest.raises(MultiValidationError, match="重复"):
        validate_multi_condition(multi_payload(queries=[_condition("a"), _condition("a", metric_id=2)]))

    with pytest.raises(MultiValidationError, match="额外维度"):
        validate_multi_condition(
            multi_payload(
                queries=[
                    _condition("a", group_by=["instance_id"]),
                    _condition("b", group_by=["instance_id", "device"]),
                ]
            )
        )


def test_validate_multi_rejects_bad_threshold_shape_and_missing_name():
    with pytest.raises(MultiValidationError, match="结果名称"):
        validate_multi_condition(multi_payload(result_name=""))

    with pytest.raises(MultiValidationError, match="全部满足"):
        validate_multi_condition(multi_payload(combinator="any"))

    with pytest.raises(MultiValidationError, match="不能带级别"):
        validate_multi_condition(
            multi_payload(
                queries=[
                    _condition("a"),
                    _condition("c", role="gate", threshold=[{"level": "warning", "method": ">", "value": 1}]),
                ]
            )
        )

    with pytest.raises(MultiValidationError, match="重复"):
        validate_multi_condition(
            multi_payload(
                queries=[
                    _condition(
                        "a",
                        threshold=[
                            {"level": "warning", "method": ">", "value": 80},
                            {"level": "warning", "method": ">", "value": 90},
                        ],
                    ),
                    _condition("b"),
                ]
            )
        )


def test_validate_multi_allows_per_series_algorithm_and_requires_count_predicate():
    payload = multi_payload(
        queries=[
            _condition("a", algorithm="rate"),
            _condition("b", algorithm="changes"),
        ]
    )
    assert validate_multi_condition(payload).anchor_ref == "a"

    with pytest.raises(MultiValidationError, match="条件计数"):
        validate_multi_condition(
            multi_payload(queries=[_condition("a", algorithm="count_if_over_time"), _condition("b")])
        )


def test_validate_multi_rejects_anchor_without_instance_id():
    with pytest.raises(MultiValidationError, match="instance_id"):
        validate_multi_condition(
            multi_payload(
                queries=[
                    _condition("a", group_by=["device"]),
                    _condition("b", group_by=["device"]),
                ]
            )
        )


def _operand(ref, metric_id=11, group_by=None):
    return {
        "ref": ref,
        "metric_id": metric_id,
        "filter": [],
        "group_algorithm": "sum",
        "group_by": group_by or ["instance_id"],
    }


def _formula_condition(ref="a", **overrides):
    data = {
        "ref": ref,
        "source": "formula",
        "metric_name": "错误率",
        "expression": "a1 / a2 * 100",
        "operands": [_operand("a1", 11), _operand("a2", 12)],
        "group_by": ["instance_id"],
        "algorithm": "avg_over_time",
        "metric_unit": "",
        "calculation_unit": "percent",
        "threshold_unit": "percent",
        "role": "level",
        "threshold": [
            {"level": "warning", "method": ">", "value": 5},
            {"level": "error", "method": ">", "value": 10},
            {"level": "critical", "method": ">", "value": 20},
        ],
    }
    data.update(overrides)
    return data


def test_validate_multi_accepts_formula_condition_and_repeated_operand_refs():
    payload = multi_payload(
        queries=[
            _formula_condition("a"),
            _formula_condition(
                "b",
                role="gate",
                metric_name="写命中率",
                threshold=[{"method": ">", "value": 1}],
            ),
        ]
    )

    result = validate_multi_condition(payload)

    assert result.anchor_ref == "a"
    assert payload["queries"][0]["operands"][0]["metric_id"] == 11
    assert payload["queries"][1]["operands"][0]["ref"] == "a1"


def test_validate_multi_accepts_count_if_formula_condition():
    payload = multi_payload(
        queries=[
            _formula_condition(
                "a",
                algorithm="count_if_over_time",
                count_predicate={"method": ">", "value": 1},
                calculation_unit="count",
                threshold_unit="count",
            ),
            _condition("b", role="gate", threshold=[{"method": ">", "value": 1}]),
        ]
    )

    assert validate_multi_condition(payload).anchor_ref == "a"


def test_validate_multi_accepts_payload_without_source():
    payload = multi_payload()

    assert validate_multi_condition(payload).anchor_ref == "a"
    assert "source" not in payload["queries"][0]


def test_validate_multi_rejects_formula_condition_shape_errors():
    with pytest.raises(MultiValidationError, match="结果名称"):
        validate_multi_condition(
            multi_payload(queries=[_formula_condition("a", metric_name="  "), _condition("b")])
        )
    with pytest.raises(MultiValidationError, match="两个操作数"):
        validate_multi_condition(
            multi_payload(
                queries=[
                    _formula_condition("a", operands=[_operand("a1")]),
                    _condition("b"),
                ]
            )
        )
    with pytest.raises(MultiValidationError, match="未被表达式引用"):
        validate_multi_condition(
            multi_payload(
                queries=[
                    _formula_condition("a", operands=[_operand("a1"), _operand("a2"), _operand("a3")]),
                    _condition("b"),
                ]
            )
        )
    with pytest.raises(MultiValidationError, match="不存在的指标变量"):
        validate_multi_condition(
            multi_payload(
                queries=[
                    _formula_condition("a", expression="a1 / a3 * 100"),
                    _condition("b"),
                ]
            )
        )
    with pytest.raises(MultiValidationError, match="第一个操作数"):
        validate_multi_condition(
            multi_payload(
                queries=[
                    _formula_condition(
                        "a",
                        group_by=["instance_id", "device"],
                        operands=[_operand("a1"), _operand("a2")],
                    ),
                    _condition("b"),
                ]
            )
        )
    with pytest.raises(MultiValidationError, match="逐序列"):
        validate_multi_condition(
            multi_payload(queries=[_formula_condition("a", algorithm="rate"), _condition("b")])
        )
    with pytest.raises(MultiValidationError, match="来源非法"):
        validate_multi_condition(
            multi_payload(queries=[_condition("a", source="promql"), _condition("b")])
        )
