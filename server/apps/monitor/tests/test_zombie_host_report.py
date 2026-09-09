"""僵尸机拼表纯函数：阈值、-1、登录未采集、IO 折叠、主机上限。"""

import json

import pytest

from apps.monitor.services.zombie_host_report import (
    DEFAULT_THRESHOLDS,
    MAX_HOSTS,
    UNBOUNDED,
    ZOMBIE_METRIC_SPECS,
    apply_thresholds,
    fold_io_max,
    parse_threshold,
    range_window,
    round_display_metrics,
    row_passes,
    validate_inst_uuids,
)

pytestmark = pytest.mark.unit


def _focused_threshold(**overrides):
    raw = {key: UNBOUNDED for key in DEFAULT_THRESHOLDS}
    raw.update(overrides)
    return parse_threshold(raw)


def test_minus_one_skips_bound():
    t = _focused_threshold(login_max=9)
    assert row_passes({"login_count": 0, "login_status": "counted"}, t) is True
    assert row_passes({"login_count": 10, "login_status": "counted"}, t) is False


def test_uncollected_skips_login_threshold_but_keeps_other_filters():
    t = _focused_threshold(login_max=9, cpu_avg_max=19)
    assert row_passes({"login_status": "uncollected", "login_count": None, "cpu_avg": 5}, t) is True
    assert row_passes({"login_status": "uncollected", "login_count": None, "cpu_avg": 50}, t) is False


def test_io_fold_takes_max_disk():
    series = [
        {"instance_id": "m1", "device": "sda", "value": 10},
        {"instance_id": "m1", "device": "sdb", "value": 40},
        {"instance_id": "m2", "device": "sda", "value": 3},
    ]
    assert fold_io_max(series) == {"m1": 40.0, "m2": 3.0}


def test_parse_threshold_empty_fills_defaults():
    parsed = parse_threshold({})
    assert parsed == DEFAULT_THRESHOLDS
    assert parsed is not DEFAULT_THRESHOLDS
    assert parsed["login_max"] == 2
    assert parsed["login_min"] == UNBOUNDED
    assert parsed["io_max_max"] == 10
    assert parsed["cpu_avg_max"] == 8


def test_parse_threshold_parses_string_bounds():
    parsed = parse_threshold({"login_min": "-1", "login_max": "9"})
    assert parsed["login_min"] == UNBOUNDED
    assert parsed["login_max"] == 9


def test_login_count_closed_interval_includes_max():
    t = _focused_threshold(login_max=9)
    assert row_passes({"login_count": 9, "login_status": "counted"}, t) is True
    assert row_passes({"login_count": 10, "login_status": "counted"}, t) is False


def test_row_passes_ands_across_metrics():
    t = _focused_threshold(login_max=9, cpu_avg_max=19)
    assert row_passes({"login_count": 1, "login_status": "counted", "cpu_avg": 5}, t) is True
    assert row_passes({"login_count": 1, "login_status": "counted", "cpu_avg": 50}, t) is False
    assert row_passes({"login_count": 10, "login_status": "counted", "cpu_avg": 5}, t) is False


def test_apply_thresholds_keeps_passing_rows_in_order():
    t = _focused_threshold(login_max=9, cpu_avg_max=19)
    rows = [
        {"host_name": "keep-a", "login_count": 1, "login_status": "counted", "cpu_avg": 5},
        {"host_name": "drop-cpu", "login_count": 1, "login_status": "counted", "cpu_avg": 50},
        {"host_name": "keep-b", "login_count": 0, "login_status": "counted", "cpu_avg": 0},
        {"host_name": "drop-login", "login_count": 10, "login_status": "counted", "cpu_avg": 1},
    ]
    kept = apply_thresholds(rows, t)
    assert [row["host_name"] for row in kept] == ["keep-a", "keep-b"]
    assert kept[0] is rows[0]
    assert kept[1] is rows[2]


def test_absent_field_treated_like_none_for_set_bounds():
    t = _focused_threshold(login_max=9, cpu_avg_max=19)

    assert row_passes({"login_count": 0, "login_status": "counted"}, t) is False
    assert row_passes({"login_status": "counted"}, t) is False
    assert row_passes({"login_status": "uncollected", "cpu_avg": 5}, t) is True
    assert row_passes({"login_status": "uncollected", "cpu_avg": 50}, t) is False


def test_missing_metric_fails_set_max_bound_except_uncollected_login():
    t = _focused_threshold(login_max=9, cpu_avg_max=19)
    assert (
        row_passes(
            {"login_count": 0, "login_status": "counted", "cpu_avg": None},
            t,
        )
        is False
    )
    assert (
        row_passes(
            {"login_count": None, "login_status": "uncollected", "cpu_avg": 5},
            t,
        )
        is True
    )
    assert (
        row_passes(
            {"login_count": None, "login_status": "counted", "cpu_avg": 5},
            t,
        )
        is False
    )


def test_unbounded_io_allows_missing_value():
    t = _focused_threshold(cpu_avg_max=19)
    assert row_passes({"cpu_avg": 5, "io_max": None}, t) is True


def test_validate_inst_uuids_empty_list_ok():
    assert validate_inst_uuids([]) == []


def test_validate_inst_uuids_rejects_non_list():
    with pytest.raises((TypeError, ValueError)):
        validate_inst_uuids(None)
    with pytest.raises((TypeError, ValueError)):
        validate_inst_uuids("u1")
    with pytest.raises((TypeError, ValueError)):
        validate_inst_uuids(("u1",))


def test_validate_inst_uuids_dedupes_and_drops_empty():
    assert validate_inst_uuids(["u1", "", "  ", "u1", "u2", None]) == ["u1", "u2"]


def test_validate_inst_uuids_rejects_more_than_max_hosts():
    with pytest.raises(ValueError, match="一次最多查询 100 台主机"):
        validate_inst_uuids([f"u{i}" for i in range(MAX_HOSTS + 1)])


def test_validate_inst_uuids_allows_exactly_max_hosts():
    values = [f"u{i}" for i in range(MAX_HOSTS)]
    assert validate_inst_uuids(values) == values


def test_fold_io_max_accepts_monitor_id_alias():
    series = [
        {"monitor_id": "m1", "device": "sda", "value": "7"},
        {"instance_id": "m1", "device": "sdb", "value": 12},
        {"monitor_id": "m2", "value": 1},
    ]
    assert fold_io_max(series) == {"m1": 12.0, "m2": 1.0}


def test_range_window_reuses_window_selector():
    assert range_window(100.0, 3700.4) == "3600s"
    assert range_window(10.0, 10.5) == "1s"


def test_metric_query_templates_join_linux_and_windows_with_or():
    cpu = ZOMBIE_METRIC_SPECS["cpu"]
    mem = ZOMBIE_METRIC_SPECS["mem"]
    packets = ZOMBIE_METRIC_SPECS["packets"]
    io = ZOMBIE_METRIC_SPECS["io"]

    assert cpu["fold"] == "identity"
    assert cpu["windows"] == ("avg", "max")
    assert "cpu_usage_idle" in cpu["query"]
    assert "cpu_usage_total_gauge_value" in cpu["query"]
    assert "host_cpu_usage_percent_gauge" in cpu["query"]
    assert " or " in cpu["query"]

    assert mem["fold"] == "identity"
    assert mem["windows"] == ("avg", "max")
    assert "mem_used_percent" in mem["query"]
    assert "mem_used_percent_gauge_value" in mem["query"]
    assert " or " in mem["query"]

    assert packets["fold"] == "sum"
    assert packets["windows"] == ("avg", "max")
    assert "rate(net_packets_recv" in packets["query"]
    assert "net_packets_recv_gauge_value" in packets["query"]
    assert " or " in packets["query"]

    assert io["fold"] == "max"
    assert io["windows"] == ("max",)
    assert "diskio_io_util" in io["query"]
    assert "diskio_io_util_gauge_value" in io["query"]


def test_round_display_metrics_keeps_two_decimals_and_skips_login():
    rounded = round_display_metrics(
        {
            "packets_recv_avg": 24626.038127103726,
            "packets_recv_max": 143635.05657370327,
            "cpu_avg": 33.087330024813916,
            "cpu_max": 46.07,
            "mem_avg": 45.12345,
            "mem_max": 53.14,
            "io_max": 75.169,
            "login_count": 1,
            "login_status": "counted",
            "host_name": "h1",
        }
    )
    assert rounded["packets_recv_avg"] == 24626.04
    assert rounded["packets_recv_max"] == 143635.06
    assert rounded["cpu_avg"] == 33.09
    assert rounded["cpu_max"] == 46.07
    assert rounded["mem_avg"] == 45.12
    assert rounded["mem_max"] == 53.14
    assert rounded["io_max"] == 75.17
    assert rounded["login_count"] == 1
    assert rounded["host_name"] == "h1"
    encoded = json.dumps(rounded)
    assert "038127103726" not in encoded
    assert "05657370327" not in encoded
    assert "087330024813916" not in encoded


def test_round_display_metrics_leaves_missing_metrics_none():
    rounded = round_display_metrics({"cpu_avg": None, "login_count": None, "login_status": "uncollected"})
    assert rounded["cpu_avg"] is None
    assert rounded["login_count"] is None
    assert rounded["login_status"] == "uncollected"
