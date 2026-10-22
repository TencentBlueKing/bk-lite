"""多指标条件判定：级别取最低，事件形状与 calculate_alerts 一致。"""

import pytest

from apps.monitor.tasks.utils.policy_calculate_multi import calculate_multi_alerts

pytestmark = pytest.mark.unit


def _series(labels, values):
    return {"metric": labels, "values": [[index + 1, str(value)] for index, value in enumerate(values)]}


def _level(ref, group_by, thresholds):
    return {
        "ref": ref,
        "role": "level",
        "group_by": group_by,
        "threshold": thresholds,
        "metric_unit": "percent",
        "calculation_unit": "percent",
        "threshold_unit": "percent",
    }


def _stairs():
    return [
        {"level": "critical", "method": ">", "value": 90},
        {"level": "warning", "method": ">", "value": 80},
    ]


def _context():
    return {
        "metric_name": "CPU 与内存双高",
        "instance_id_keys": ["instance_id"],
        "monitor_instance_id_key": "instance_id",
        "instances_map": {"('h1',)": "主机1"},
        "condition_display_units": {"a": "%", "b": "%", "c": "s"},
        "condition_metric_names": {"a": "CPU 使用率", "b": "内存使用率", "c": "系统运行时长"},
    }


def _run(series_by_ref, conditions, n=1, alert_name="${value} ${a_value} ${b_metric_name}"):
    return calculate_multi_alerts(alert_name, series_by_ref, conditions, _context(), n=n)


def test_level_is_the_lower_of_the_two_hits():
    conditions = [
        _level("a", ["instance_id"], _stairs()),
        _level("b", ["instance_id"], _stairs()),
    ]
    warning_alerts, warning_infos, holds = _run(
        {
            "a": [_series({"instance_id": "h1"}, [92])],
            "b": [_series({"instance_id": "h1"}, [87.5])],
        },
        conditions,
    )
    critical_alerts, _, _ = _run(
        {
            "a": [_series({"instance_id": "h1"}, [93])],
            "b": [_series({"instance_id": "h1"}, [96])],
        },
        conditions,
    )
    missed_alerts, missed_infos, _ = _run(
        {
            "a": [_series({"instance_id": "h1"}, [95])],
            "b": [_series({"instance_id": "h1"}, [61])],
        },
        conditions,
    )

    assert holds == []
    assert warning_alerts[0]["level"] == "warning"
    assert warning_alerts[0]["value"] == 92
    assert critical_alerts[0]["level"] == "critical"
    assert critical_alerts[0]["value"] == 93
    assert missed_alerts == []
    assert missed_infos[0]["level"] == "info"
    assert set(missed_infos[0]["raw_data"]["series"]) == {"a", "b"}
    assert "92.00%" in warning_alerts[0]["content"]
    assert "内存使用率" in warning_alerts[0]["content"]


def test_gate_blocks_even_when_level_conditions_are_critical():
    alerts, infos, holds = _run(
        {
            "a": [_series({"instance_id": "h1"}, [95])],
            "b": [_series({"instance_id": "h1"}, [96])],
            "c": [_series({"instance_id": "h1"}, [240])],
        },
        [
            _level("a", ["instance_id"], _stairs()),
            _level("b", ["instance_id"], _stairs()),
            {
                "ref": "c",
                "role": "gate",
                "group_by": ["instance_id"],
                "threshold": [{"method": ">", "value": 600}],
            },
        ],
    )

    assert alerts == []
    assert holds == []
    assert infos[0]["value"] == 95


def test_subset_dimension_broadcasts_host_value_onto_each_partition():
    alerts, infos, holds = calculate_multi_alerts(
        "$value",
        {
            "a": [
                _series({"instance_id": "h1", "device": "sda"}, [91]),
                _series({"instance_id": "h1", "device": "sdb"}, [88]),
            ],
            "b": [_series({"instance_id": "h1"}, [96])],
        },
        [
            _level("a", ["instance_id", "device"], _stairs()),
            _level("b", ["instance_id"], _stairs()),
        ],
        {
            "metric_name": "磁盘与内存",
            "instance_id_keys": ["instance_id", "device"],
            "monitor_instance_id_key": "instance_id",
            "instances_map": {"('h1',)": "主机1"},
            "condition_display_units": {"a": "%", "b": "%"},
            "condition_metric_names": {"a": "磁盘使用率", "b": "内存使用率"},
        },
    )

    assert infos == []
    assert holds == []
    assert {item["metric_instance_id"] for item in alerts} == {"('h1', 'sda')", "('h1', 'sdb')"}
    assert {item["raw_data"]["condition_values"]["b"] for item in alerts} == {96}
    assert alerts[0]["value"] == alerts[0]["raw_data"]["condition_values"]["a"]


def test_trigger_count_uses_intersection_and_skips_a_short_row():
    conditions = [
        _level("a", ["instance_id"], _stairs()),
        _level("b", ["instance_id"], _stairs()),
    ]
    alerts, infos, _ = _run(
        {
            "a": [_series({"instance_id": "h1"}, [95, 85])],
            "b": [_series({"instance_id": "h1"}, [96, 85])],
        },
        conditions,
        n=2,
    )
    skipped, skipped_infos, _ = _run(
        {
            "a": [_series({"instance_id": "h1"}, [95, 85])],
            "b": [_series({"instance_id": "h1"}, [96])],
        },
        conditions,
        n=2,
    )

    assert infos == []
    assert alerts[0]["level"] == "warning"
    assert skipped == []
    assert skipped_infos == []


def test_missing_non_anchor_series_is_not_classified():
    alerts, infos, holds = _run(
        {"a": [_series({"instance_id": "h1"}, [86])], "b": []},
        [
            _level("a", ["instance_id"], _stairs()),
            _level("b", ["instance_id"], _stairs()),
        ],
    )

    assert alerts == []
    assert infos == []
    assert holds == []


def test_value_comes_from_the_first_level_condition_when_anchor_is_gate():
    alerts, infos, _ = _run(
        {
            "c": [_series({"instance_id": "h1"}, [900])],
            "a": [_series({"instance_id": "h1"}, [93])],
        },
        [
            {
                "ref": "c",
                "role": "gate",
                "group_by": ["instance_id"],
                "threshold": [{"method": ">", "value": 600}],
            },
            _level("a", ["instance_id"], _stairs()),
        ],
        alert_name="${value} ${a_value} ${c_metric_name}",
    )

    assert infos == []
    assert alerts[0]["value"] == 93
    assert "93.00%" in alerts[0]["content"]
    assert "系统运行时长" in alerts[0]["content"]
    assert set(alerts[0]["raw_data"]["series"]) == {"a", "c"}
