import pydantic.root_model  # noqa

from apps.log.services.search import SearchService


# ----------------------- _apply_default_time_window -----------------------


def test_apply_default_time_window_fills_when_both_empty():
    start, end = SearchService._apply_default_time_window("", "")
    assert start.endswith("Z") and end.endswith("Z")
    assert start < end  # start 比 end 早 15 分钟


def test_apply_default_time_window_keeps_provided_values():
    start, end = SearchService._apply_default_time_window("2024-01-01", "2024-01-02")
    assert (start, end) == ("2024-01-01", "2024-01-02")


def test_apply_default_time_window_keeps_partial_values():
    # 只要有一个非空就不覆盖
    start, end = SearchService._apply_default_time_window("2024-01-01", "")
    assert (start, end) == ("2024-01-01", "")


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
    out = SearchService.field_values("2024-01-01", "2024-01-02", "host", limit=20, query="q", log_groups=["g1"])
    assert out == {"values": [{"value": "x"}]}
    vm.field_values.assert_called_once_with("2024-01-01", "2024-01-02", "host", 20, query="FINAL_Q")


def test_field_names_forwards_to_field_values(mocker):
    fv = mocker.patch("apps.log.services.search.SearchService.field_values", return_value={"v": 1})
    out = SearchService.field_names("s", "e", "host", limit=5, query="q", log_groups=["g"])
    assert out == {"v": 1}
    fv.assert_called_once_with("s", "e", "host", 5, query="q", log_groups=["g"])


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
    out = SearchService.all_field_names("q", "s", "e")
    assert out == ["app", "host"]


def test_all_field_names_non_dict_response_yields_empty(mocker):
    mocker.patch(
        "apps.log.services.search.LogGroupQueryBuilder.build_query_with_groups",
        return_value=("FQ", []),
    )
    vm = mocker.patch("apps.log.services.search.VictoriaMetricsAPI").return_value
    vm.all_field_names.return_value = ["unexpected"]
    assert SearchService.all_field_names("q", "s", "e") == []


# ----------------------- search_logs -----------------------


def test_search_logs_appends_group_info_for_dict_response(mocker):
    mocker.patch(
        "apps.log.services.search.LogGroupQueryBuilder.build_query_with_groups",
        return_value=("FQ", [{"id": "g1"}]),
    )
    vm = mocker.patch("apps.log.services.search.VictoriaMetricsAPI").return_value
    vm.query.return_value = {"data": [1]}
    out = SearchService.search_logs("q", "s", "e", limit=3, log_groups=["g1"])
    assert out == {"data": [1], "_log_group_info": [{"id": "g1"}]}
    vm.query.assert_called_once_with("FQ", "s", "e", 3)


def test_search_logs_list_response_returned_as_is(mocker):
    mocker.patch(
        "apps.log.services.search.LogGroupQueryBuilder.build_query_with_groups",
        return_value=("FQ", [{"id": "g1"}]),
    )
    vm = mocker.patch("apps.log.services.search.VictoriaMetricsAPI").return_value
    vm.query.return_value = [{"a": 1}]
    out = SearchService.search_logs("q", "s", "e")
    assert out == [{"a": 1}]


# ----------------------- search_hits -----------------------


def test_search_hits_attaches_group_info(mocker):
    mocker.patch(
        "apps.log.services.search.LogGroupQueryBuilder.build_query_with_groups",
        return_value=("FQ", [{"id": "g"}]),
    )
    vm = mocker.patch("apps.log.services.search.VictoriaMetricsAPI").return_value
    vm.hits.return_value = {"hits": []}
    out = SearchService.search_hits("q", "s", "e", "host", fields_limit=2, step="1m", log_groups=["g"])
    assert out["_log_group_info"] == [{"id": "g"}]
    vm.hits.assert_called_once_with("FQ", "s", "e", "host", 2, "1m")


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
    out = SearchService.top_stats("q", "s", "e", "host", top_num=2, log_groups=["g"])
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
    out = SearchService.top_stats("q", "s", "e", "host")
    assert out["total"] == 0
    assert out["items"][0]["ratio"] == 0.0
    assert "_log_group_info" not in out
