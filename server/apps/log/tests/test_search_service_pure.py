import pydantic.root_model  # noqa

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from apps.core.utils.time_util import format_rfc3339_utc
from apps.log.services.search import SearchService
from apps.log.utils.log_group import LogGroupQueryBuilder


pytestmark = pytest.mark.unit

WINDOW_START = "2026-04-22T00:00:00.000Z"
WINDOW_END = "2026-04-22T00:15:00.000Z"
SEVEN_DAY_START = "2026-04-01T00:00:00.000Z"
SEVEN_DAY_END = "2026-04-08T00:00:00.000Z"
THIRTY_DAY_START = "2026-04-01T00:00:00.000Z"
THIRTY_DAY_END = "2026-05-01T00:00:00.000Z"
OVERSIZED_START = "2026-01-01T00:00:00.000Z"
OVERSIZED_END = "2026-02-02T00:00:00.000Z"


# ----------------------- _apply_default_time_window -----------------------


def test_apply_default_time_window_fills_when_both_empty():
    start, end = SearchService._apply_default_time_window("", "")
    assert start.endswith("Z") and end.endswith("Z")
    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
    assert end_dt - start_dt == timedelta(minutes=15)


def test_apply_default_time_window_keeps_provided_rfc3339():
    start, end = SearchService._apply_default_time_window(WINDOW_START, WINDOW_END)
    assert (start, end) == (WINDOW_START, WINDOW_END)


def test_apply_default_time_window_fills_missing_end():
    start_input = format_rfc3339_utc(datetime.now(timezone.utc) - timedelta(minutes=10))
    start, end = SearchService._apply_default_time_window(start_input, "")
    assert start == start_input
    assert end.endswith("Z")
    assert start < end


def test_apply_default_time_window_rejects_stale_start_after_filling_end():
    with pytest.raises(ValueError):
        SearchService._apply_default_time_window(WINDOW_START, "")


def test_apply_default_time_window_fills_missing_start():
    start, end = SearchService._apply_default_time_window("", WINDOW_END)
    assert (start, end) == (WINDOW_START, WINDOW_END)


def test_apply_default_time_window_rejects_illegal_and_timezone_less_values():
    with pytest.raises(ValueError):
        SearchService._apply_default_time_window("2024-01-01", "2024-01-02")
    with pytest.raises(ValueError):
        SearchService._apply_default_time_window("2026-04-22T00:00:00", "2026-04-22T00:15:00")


def test_apply_default_time_window_rejects_end_not_after_start():
    with pytest.raises(ValueError):
        SearchService._apply_default_time_window(WINDOW_END, WINDOW_START)


def test_apply_default_time_window_accepts_seven_and_thirty_day_range():
    assert SearchService._apply_default_time_window(SEVEN_DAY_START, SEVEN_DAY_END) == (SEVEN_DAY_START, SEVEN_DAY_END)
    assert SearchService._apply_default_time_window(THIRTY_DAY_START, THIRTY_DAY_END) == (THIRTY_DAY_START, THIRTY_DAY_END)


def test_apply_default_time_window_rejects_oversized_range():
    with pytest.raises(ValueError):
        SearchService._apply_default_time_window(OVERSIZED_START, OVERSIZED_END)


def test_search_logs_rejects_oversized_range_without_vm_query(mocker):
    vm = mocker.patch("apps.log.services.search.VictoriaMetricsAPI").return_value

    with pytest.raises(ValueError):
        SearchService.search_logs("q", OVERSIZED_START, OVERSIZED_END)

    vm.query.assert_not_called()


# ----------------------- _compact_query -----------------------


def test_compact_query_strips_and_keeps_short():
    assert SearchService._compact_query("  hello  ") == "hello"


def test_compact_query_truncates_long():
    out = SearchService._compact_query("a" * 500, limit=10)
    assert out == "a" * 10 + "..."


def test_compact_query_handles_none():
    assert SearchService._compact_query(None) == ""


# ----------------------- _append_filter -----------------------


def test_append_filter_returns_filter_when_base_empty():
    assert SearchService._append_filter("", "host:*") == "host:*"
    assert SearchService._append_filter("*", "host:*") == "host:*"
    assert SearchService._append_filter(None, "host:*") == "host:*"


def test_append_filter_wraps_base_query():
    assert SearchService._append_filter("level:error", "host:*") == "(level:error) AND host:*"


def test_build_storage_query_maps_logical_message_added_by_log_group(mocker):
    mocker.patch(
        "apps.log.services.search.LogGroupQueryBuilder.build_query_with_groups",
        return_value=('message:"failed" AND host:*', [{"id": "g1"}]),
    )

    query, group_info = SearchService._build_storage_query("*", ["g1"])

    assert query == '_msg:"failed" AND host:*'
    assert group_info == [{"id": "g1"}]


def test_build_storage_query_normalizes_empty_and_metadata_filters():
    query, group_info = SearchService._build_storage_query("message:", None)
    assert query == "_msg:*"
    assert group_info == []

    quoted, _ = SearchService._build_storage_query("@metadata.beat:", None)
    assert quoted == '"@metadata.beat":*'


def test_build_storage_query_denies_unknown_rule_mode_without_mocking_builder():
    group = SimpleNamespace(
        id="g1",
        name="group",
        rule={"mode": "ADN", "conditions": [{"field": "cluster", "op": "==", "value": "prod"}]},
    )

    query, group_info = SearchService._build_storage_query("host:web", ["g1"], resolved_groups=[group])

    assert query == LogGroupQueryBuilder.DENY_ALL_QUERY
    assert group_info[0]["status"] == "invalid_rule"


def test_build_storage_query_applies_explicit_legacy_or_without_mocking_builder(settings):
    settings.LOG_GROUP_LEGACY_OR_GROUP_IDS = frozenset({"g1"})
    group = SimpleNamespace(
        id="g1",
        name="group",
        rule={
            "mode": "ADN",
            "conditions": [
                {"field": "cluster", "op": "==", "value": "prod"},
                {"field": "namespace", "op": "==", "value": "blue"},
            ],
        },
    )

    query, group_info = SearchService._build_storage_query("host:web", ["g1"], resolved_groups=[group])

    assert query == '(host:web) AND ((cluster:"prod" OR namespace:"blue"))'
    assert group_info[0]["status"] == "legacy_or"


# ----------------------- _normalize_count -----------------------


def test_normalize_count_handles_empty():
    assert SearchService._normalize_count(None) == 0
    assert SearchService._normalize_count("") == 0


def test_normalize_count_parses_numeric_string():
    assert SearchService._normalize_count("42") == 42
    assert SearchService._normalize_count("42.9") == 42
    assert SearchService._normalize_count(7) == 7


def test_normalize_count_invalid_returns_zero():
    assert SearchService._normalize_count("abc") == 0


# ----------------------- _build_ratio -----------------------


def test_build_ratio_zero_total():
    assert SearchService._build_ratio(5, 0) == 0.0


def test_build_ratio_rounds_half_up():
    # 1/3 = 0.3333
    assert SearchService._build_ratio(1, 3) == 0.3333


def test_build_ratio_exact():
    assert SearchService._build_ratio(1, 4) == 0.25


# ----------------------- field_values / all_field_names -----------------------


def test_field_values_forwards_final_query_to_api(mocker):
    mocker.patch(
        "apps.log.services.search.LogGroupQueryBuilder.build_query_with_groups",
        return_value=("FINAL_Q", [{"id": "g1"}]),
    )
    vm = mocker.patch("apps.log.services.search.VictoriaMetricsAPI").return_value
    vm.field_values.return_value = {"values": [{"value": "x"}]}
    out = SearchService.field_values(WINDOW_START, WINDOW_END, "host", limit=20, query="q", log_groups=["g1"])
    assert out == {"values": [{"value": "x"}]}
    vm.field_values.assert_called_once_with(WINDOW_START, WINDOW_END, "host", 20, query="FINAL_Q")


def test_field_values_maps_logical_message_to_storage_field(mocker):
    mocker.patch("apps.log.services.search.LogGroupQueryBuilder.build_query_with_groups", return_value=("FINAL_Q", []))
    vm = mocker.patch("apps.log.services.search.VictoriaMetricsAPI").return_value
    vm.field_values.return_value = {"values": []}

    SearchService.field_values(WINDOW_START, WINDOW_END, "message", query="q")

    vm.field_values.assert_called_once_with(WINDOW_START, WINDOW_END, "_msg", 100, query="FINAL_Q")


def test_field_values_skips_exists_filter_for_stream_id(mocker):
    builder = mocker.patch(
        "apps.log.services.search.LogGroupQueryBuilder.build_query_with_groups",
        return_value=("FINAL_Q", []),
    )
    vm = mocker.patch("apps.log.services.search.VictoriaMetricsAPI").return_value
    vm.field_values.return_value = {"values": []}

    SearchService.field_values(WINDOW_START, WINDOW_END, "_stream_id", query="*")

    assert builder.call_args.args[0] == "*"
    vm.field_values.assert_called_once_with(WINDOW_START, WINDOW_END, "_stream_id", 100, query="FINAL_Q")


def test_field_values_quotes_metadata_exists_filter(mocker):
    builder = mocker.patch(
        "apps.log.services.search.LogGroupQueryBuilder.build_query_with_groups",
        return_value=("FINAL_Q", []),
    )
    mocker.patch("apps.log.services.search.VictoriaMetricsAPI").return_value.field_values.return_value = {"values": []}

    SearchService.field_values(WINDOW_START, WINDOW_END, "@metadata.beat", query="*")

    assert builder.call_args.args[0] == '"@metadata.beat":*'


def test_field_names_forwards_to_field_values(mocker):
    fv = mocker.patch("apps.log.services.search.SearchService.field_values", return_value={"v": 1})
    out = SearchService.field_names(WINDOW_START, WINDOW_END, "host", limit=5, query="q", log_groups=["g"])
    assert out == {"v": 1}
    fv.assert_called_once_with(WINDOW_START, WINDOW_END, "host", 5, query="q", log_groups=["g"])


def test_all_field_names_extracts_and_sorts_unique_strings(mocker):
    mocker.patch(
        "apps.log.services.search.LogGroupQueryBuilder.build_query_with_groups",
        return_value=("FQ", []),
    )
    vm = mocker.patch("apps.log.services.search.VictoriaMetricsAPI").return_value
    vm.all_field_names.return_value = {
        "values": [
            {"value": "host"},
            {"value": "host"},  # 去重
            {"value": "app"},
            {"value": ""},  # 空串忽略
            {"value": 5},  # 非字符串忽略
            "not-a-dict",  # 非 dict 忽略
        ]
    }
    out = SearchService.all_field_names("q", WINDOW_START, WINDOW_END)
    assert out == ["app", "host"]


def test_all_field_names_non_dict_response_yields_empty(mocker):
    mocker.patch(
        "apps.log.services.search.LogGroupQueryBuilder.build_query_with_groups",
        return_value=("FQ", []),
    )
    vm = mocker.patch("apps.log.services.search.VictoriaMetricsAPI").return_value
    vm.all_field_names.return_value = ["unexpected"]
    assert SearchService.all_field_names("q", WINDOW_START, WINDOW_END) == []


def test_all_field_names_hides_victoria_logs_message_field(mocker):
    mocker.patch("apps.log.services.search.LogGroupQueryBuilder.build_query_with_groups", return_value=("FQ", []))
    vm = mocker.patch("apps.log.services.search.VictoriaMetricsAPI").return_value
    vm.all_field_names.return_value = {"values": [{"value": "_msg"}, {"value": "message"}]}

    assert SearchService.all_field_names("q", WINDOW_START, WINDOW_END) == ["message"]


def test_all_field_names_hides_beat_timestamp_field(mocker):
    mocker.patch("apps.log.services.search.LogGroupQueryBuilder.build_query_with_groups", return_value=("FQ", []))
    vm = mocker.patch("apps.log.services.search.VictoriaMetricsAPI").return_value
    vm.all_field_names.return_value = {
        "values": [{"value": "@timestamp"}, {"value": "_stream_id"}, {"value": "timestamp"}, {"value": "host"}]
    }

    assert SearchService.all_field_names("q", WINDOW_START, WINDOW_END) == ["host", "timestamp"]


# ----------------------- search_logs -----------------------


def test_search_logs_appends_group_info_for_dict_response(mocker):
    mocker.patch(
        "apps.log.services.search.LogGroupQueryBuilder.build_query_with_groups",
        return_value=("FQ", [{"id": "g1"}]),
    )
    vm = mocker.patch("apps.log.services.search.VictoriaMetricsAPI").return_value
    vm.query.return_value = {"data": [1]}
    out = SearchService.search_logs("q", WINDOW_START, WINDOW_END, limit=3, log_groups=["g1"])
    assert out == {"data": [1], "_log_group_info": [{"id": "g1"}]}
    vm.query.assert_called_once_with("FQ", WINDOW_START, WINDOW_END, 3)


def test_search_logs_list_response_returned_as_is(mocker):
    mocker.patch(
        "apps.log.services.search.LogGroupQueryBuilder.build_query_with_groups",
        return_value=("FQ", [{"id": "g1"}]),
    )
    vm = mocker.patch("apps.log.services.search.VictoriaMetricsAPI").return_value
    vm.query.return_value = [{"a": 1}]
    out = SearchService.search_logs("q", WINDOW_START, WINDOW_END)
    assert out == [{"a": 1}]


def test_search_logs_exposes_only_logical_message(mocker):
    mocker.patch("apps.log.services.search.LogGroupQueryBuilder.build_query_with_groups", return_value=("FQ", []))
    vm = mocker.patch("apps.log.services.search.VictoriaMetricsAPI").return_value
    vm.query.return_value = [{"_msg": "hello", "host": "node-1"}]

    assert SearchService.search_logs("q", WINDOW_START, WINDOW_END) == [{"message": "hello", "host": "node-1"}]


# ----------------------- search_hits -----------------------


def test_search_hits_attaches_group_info(mocker):
    mocker.patch(
        "apps.log.services.search.LogGroupQueryBuilder.build_query_with_groups",
        return_value=("FQ", [{"id": "g"}]),
    )
    vm = mocker.patch("apps.log.services.search.VictoriaMetricsAPI").return_value
    vm.hits.return_value = {"hits": []}
    out = SearchService.search_hits("q", WINDOW_START, WINDOW_END, "host", fields_limit=2, step="1m", log_groups=["g"])
    assert out["_log_group_info"] == [{"id": "g"}]
    vm.hits.assert_called_once_with("FQ", WINDOW_START, WINDOW_END, "host", 2, "1m")


def test_search_hits_maps_logical_message_field(mocker):
    mocker.patch("apps.log.services.search.LogGroupQueryBuilder.build_query_with_groups", return_value=("FQ", []))
    vm = mocker.patch("apps.log.services.search.VictoriaMetricsAPI").return_value
    vm.hits.return_value = {"hits": []}

    SearchService.search_hits("q", WINDOW_START, WINDOW_END, "message")

    vm.hits.assert_called_once_with("FQ", WINDOW_START, WINDOW_END, "_msg", 5, "5m")


# ----------------------- top_stats -----------------------


def test_top_stats_builds_items_with_ratio(mocker):
    mocker.patch(
        "apps.log.services.search.LogGroupQueryBuilder.build_query_with_groups",
        return_value=("FQ", [{"id": "g"}]),
    )
    vm = mocker.patch("apps.log.services.search.VictoriaMetricsAPI").return_value
    # 第一次 query 返回总数，第二次返回 TopN
    vm.query.side_effect = [
        [{"total_count": "10"}],
        [
            {"host": "web-1", "entry_count": "6"},
            {"host": "web-2", "entry_count": "4"},
        ],
    ]
    out = SearchService.top_stats("q", WINDOW_START, WINDOW_END, "host", top_num=2, log_groups=["g"])
    assert out["attr"] == "host"
    assert out["total"] == 10
    assert out["items"][0] == {"value": "web-1", "count": 6, "ratio": 0.6}
    assert out["items"][1] == {"value": "web-2", "count": 4, "ratio": 0.4}
    assert out["_log_group_info"] == [{"id": "g"}]


def test_top_stats_zero_total_when_no_response(mocker):
    mocker.patch(
        "apps.log.services.search.LogGroupQueryBuilder.build_query_with_groups",
        return_value=("FQ", []),
    )
    vm = mocker.patch("apps.log.services.search.VictoriaMetricsAPI").return_value
    vm.query.side_effect = [[], [{"host": "a", "entry_count": "0"}]]
    out = SearchService.top_stats("q", WINDOW_START, WINDOW_END, "host")
    assert out["total"] == 0
    assert out["items"][0]["ratio"] == 0.0
    assert "_log_group_info" not in out
