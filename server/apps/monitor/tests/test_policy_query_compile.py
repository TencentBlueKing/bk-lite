"""策略查询编译：锁 MetricsQL 字符串与旧策略回归。"""
from types import SimpleNamespace

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.tasks.utils import policy_methods as pm

pytestmark = pytest.mark.unit


def _policy(**kwargs):
    base = dict(
        algorithm="avg_over_time",
        group_algorithm="avg",
        group_by=["instance_id"],
        query_condition={"type": "metric", "metric_id": 1},
        collect_type="",
        compare_mode="absolute",
        compare_value_kind="",
        metric_unit="bytes",
        calculation_unit="kibibytes",
        period={"type": "min", "value": 5},
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_legacy_absolute_compile_matches_build_policy_query():
    policy = _policy(algorithm="sum", group_algorithm=None)
    compiled = pm.compile_policy_query(policy, "cpu", "5m", "instance_id")
    assert compiled == pm.build_policy_query("sum", "cpu", "5m", "instance_id")
    assert compiled == "sum_over_time((sum(cpu) by (instance_id))[5m:10s])"


@pytest.mark.parametrize(
    "algorithm,phi",
    [
        ("p90_over_time", "0.90"),
        ("p95_over_time", "0.95"),
        ("p99_over_time", "0.99"),
    ],
)
def test_quantile_algorithms_compile_quantile_over_time(algorithm, phi):
    policy = _policy(algorithm=algorithm)
    compiled = pm.compile_policy_query(policy, "cpu", "5m", "instance_id")
    assert compiled == (
        f"quantile_over_time({phi}, ((avg(cpu) by (instance_id))[5m:10s]))"
    )


@pytest.mark.parametrize("algorithm", ["avg_over_time", "p95_over_time"])
@pytest.mark.parametrize(
    "compare_mode,kind,expected_suffix",
    [
        (
            "previous_window",
            "delta",
            " - {q} offset 5m",
        ),
        (
            "previous_window",
            "percent",
            " - {q} offset 5m) / ({q} offset 5m) * 100",
        ),
        (
            "offset_1h",
            "percent",
            " - {q} offset 1h) / ({q} offset 1h) * 100",
        ),
        (
            "offset_1h",
            "ratio",
            " / ({q} offset 1h)",
        ),
        (
            "offset_24h",
            "percent",
            " - {q} offset 24h) / ({q} offset 24h) * 100",
        ),
        (
            "offset_24h",
            "ratio",
            " / ({q} offset 24h)",
        ),
    ],
)
def test_compare_mode_wraps_window_query(algorithm, compare_mode, kind, expected_suffix):
    policy = _policy(
        algorithm=algorithm,
        compare_mode=compare_mode,
        compare_value_kind=kind,
    )
    window = pm.compile_window_query(policy, "cpu", "5m", "instance_id")
    compiled = pm.compile_policy_query(policy, "cpu", "5m", "instance_id")
    if kind == "delta":
        assert compiled == f"{window}{expected_suffix.format(q=window)}"
    elif kind == "percent":
        assert compiled == f"({window}{expected_suffix.format(q=window)}"
    else:
        assert compiled == f"{window}{expected_suffix.format(q=window)}"


def test_formula_path_then_compare_percent():
    policy = _policy(
        query_condition={"type": "formula", "expression": "a / b"},
        algorithm="avg_over_time",
        compare_mode="offset_1h",
        compare_value_kind="percent",
    )
    base = "sum(a) / sum(b)"
    window = pm.build_formula_policy_query("avg_over_time", base, "5m")
    compiled = pm.compile_policy_query(policy, base, "5m")
    assert compiled == (
        f"({window} - {window} offset 1h) / ({window} offset 1h) * 100"
    )


def test_trap_short_circuits_compare_mode():
    policy = _policy(
        collect_type="trap",
        algorithm="last_over_time",
        compare_mode="offset_1h",
        compare_value_kind="percent",
    )
    compiled = pm.compile_policy_query(policy, "trap_metric", "5m", "source")
    assert compiled == pm.build_policy_query(
        "last_over_time", "trap_metric", "5m", "source"
    )
    assert "offset" not in compiled


def test_existence_query_uses_algorithm_but_ignores_compare_mode():
    policy = _policy(
        algorithm="p95_over_time",
        group_algorithm="max",
        compare_mode="offset_1h",
        compare_value_kind="percent",
    )
    compiled = pm.compile_existence_query(policy, "cpu", "5m", "instance_id")
    assert compiled == (
        "quantile_over_time(0.95, ((max(cpu) by (instance_id))[5m:10s]))"
    )
    assert compiled == pm.compile_window_query(policy, "cpu", "5m", "instance_id")
    assert "offset" not in compiled


def test_existence_formula_uses_policy_algorithm():
    policy = _policy(query_condition={"type": "formula"}, algorithm="avg_over_time")
    compiled = pm.compile_existence_query(policy, "sum(a) / sum(b)", "5m")
    assert compiled == pm.build_formula_policy_query(
        "avg_over_time", "sum(a) / sum(b)", "5m"
    )
    assert compiled == "avg_over_time((sum(a) / sum(b))[5m:10s])"


def test_old_policy_existence_matches_pre_upgrade_aggregation():
    policy = SimpleNamespace(
        algorithm="avg",
        group_algorithm=None,
        group_by=["instance_id"],
        query_condition={"type": "pmq", "query": "up"},
        collect_type="",
    )
    expected = pm.build_policy_query("avg", "up", "5m", "instance_id")
    assert expected == "avg_over_time((avg(up) by (instance_id))[5m:10s])"
    assert pm.compile_existence_query(policy, "up", "5m", "instance_id") == expected
    assert pm.compile_policy_query(policy, "up", "5m", "instance_id") == expected


def test_offset_7d_compiles_percent():
    policy = _policy(compare_mode="offset_7d", compare_value_kind="percent")
    window = pm.compile_window_query(policy, "cpu", "5m", "instance_id")
    compiled = pm.compile_policy_query(policy, "cpu", "5m", "instance_id")
    assert compiled == f"({window} - {window} offset 7d) / ({window} offset 7d) * 100"


def test_stddev_compiles_stddev_over_time():
    policy = _policy(algorithm="stddev_over_time")
    compiled = pm.compile_policy_query(policy, "cpu", "5m", "instance_id")
    assert compiled == "stddev_over_time((avg(cpu) by (instance_id))[5m:10s])"


def test_count_if_compiles_predicate_without_bool():
    policy = _policy(
        algorithm="count_if_over_time",
        count_predicate={"method": ">", "value": 80},
    )
    compiled = pm.compile_policy_query(policy, "cpu", "5m", "instance_id")
    assert compiled == (
        "count_over_time(((avg(cpu) by (instance_id)) > 80)[5m:10s])"
    )
    assert "bool" not in compiled


def test_per_series_compiles_then_groups():
    policy = _policy(algorithm="rate", group_algorithm="avg")
    assert (
        pm.compile_policy_query(policy, "cpu", "5m", "instance_id")
        == "avg(rate(cpu[5m])) by (instance_id)"
    )
    policy = _policy(algorithm="changes", group_algorithm="max")
    assert (
        pm.compile_policy_query(policy, "up", "5m", "instance_id")
        == "max(changes(up[5m])) by (instance_id)"
    )
    policy = _policy(algorithm="deriv", group_algorithm="avg")
    assert (
        pm.compile_policy_query(policy, "disk", "5m", "instance_id")
        == "avg(deriv(disk[5m])) by (instance_id)"
    )


def test_rate_rejects_base_query_already_containing_rate():
    policy = _policy(algorithm="rate")
    with pytest.raises(BaseAppException, match="already contains rate"):
        pm.compile_policy_query(policy, "rate(if_octets[5m])", "5m", "instance_id")


def test_baseline_4w_percent_uses_four_offsets():
    policy = _policy(compare_mode="baseline_4w", compare_value_kind="percent")
    q = pm.compile_window_query(policy, "cpu", "5m", "instance_id")
    compiled = pm.compile_policy_query(policy, "cpu", "5m", "instance_id")
    b = f"({q} offset 7d + {q} offset 14d + {q} offset 21d + {q} offset 28d) / 4"
    assert compiled == f"({q} - ({b})) / ({b}) * 100"


def test_timeleft_uses_water_level_and_lookback_deriv():
    policy = _policy(
        algorithm="last_over_time",
        group_algorithm="avg",
        compare_mode="timeleft",
        compare_value_kind="hours",
        forecast_target=90,
        forecast_lookback={"type": "hour", "value": 1},
    )
    compiled = pm.compile_policy_query(policy, "disk", "5m", "instance_id")
    water = "last_over_time((avg(disk) by (instance_id))[5m:10s])"
    slope = "deriv((avg(disk) by (instance_id))[1h:2m])"
    assert compiled == f"clamp_min(90 - {water}, 0) / clamp_min({slope}, 1e-9) / 3600"


def test_existence_rate_uses_last_over_time():
    policy = _policy(algorithm="rate", group_algorithm="avg", compare_mode="offset_1h")
    compiled = pm.compile_existence_query(policy, "cpu", "5m", "instance_id")
    assert compiled == "last_over_time((avg(cpu) by (instance_id))[5m:10s])"
    assert "rate(" not in compiled
    assert "offset" not in compiled


def test_old_policy_without_new_fields_compiles_identically():
    policy = SimpleNamespace(
        algorithm="avg",
        group_algorithm=None,
        group_by=["instance_id"],
        query_condition={"type": "pmq", "query": "up"},
        collect_type="",
    )
    compiled = pm.compile_policy_query(policy, "up", "5m", "instance_id")
    assert compiled == "avg_over_time((avg(up) by (instance_id))[5m:10s])"


def test_legacy_short_algorithm_ignores_default_group_algorithm():
    policy = _policy(algorithm="avg", group_algorithm="avg")
    compiled = pm.compile_policy_query(policy, "up", "5m", "instance_id")
    assert compiled == "avg_over_time((avg(up) by (instance_id))[5m:10s])"


@pytest.mark.parametrize(
    "kwargs,unit,conversion",
    [
        ({}, "kibibytes", True),
        ({"compare_value_kind": "delta", "compare_mode": "previous_window"}, "kibibytes", True),
        ({"compare_value_kind": "percent", "compare_mode": "offset_1h"}, "percent", False),
        ({"compare_value_kind": "ratio", "compare_mode": "offset_24h"}, "", False),
        ({"algorithm": "p95_over_time"}, "kibibytes", True),
        ({"algorithm": "stddev_over_time"}, "kibibytes", True),
        ({"algorithm": "count_if_over_time"}, "count", False),
        ({"algorithm": "changes"}, "count", False),
        ({"algorithm": "rate"}, "bytes", False),
        ({"compare_value_kind": "hours", "compare_mode": "timeleft"}, "hour", False),
    ],
)
def test_resolve_result_unit(kwargs, unit, conversion):
    policy = _policy(**kwargs)
    result = pm.resolve_result_unit(policy)
    assert result.unit == unit
    assert result.conversion_enabled is conversion
