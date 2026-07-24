"""apps/log/tasks/services/policy_scan.py 纯逻辑测试。

只测无 DB/IO 的辅助方法：查询构建、聚合解析、条件比较、模板渲染等。
VictoriaMetricsAPI 在 __init__ 中被实例化（不发起连接），其方法在本文件不调用，
因此无需 mock。policy 用 SimpleNamespace 构造，避免 DB。
"""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.log.tasks.services.policy_scan import LogPolicyScan


def _policy(**overrides):
    base = dict(
        id=1,
        alert_name="",
        alert_type="keyword",
        alert_level="warning",
        alert_condition={},
        period={"type": "min", "value": 5},
        collect_type=None,
        log_groups=[],
        last_run_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _scan(**overrides):
    return LogPolicyScan(_policy(**overrides))


class TestScanWindow:
    def test_explicit_window_is_used(self):
        scan = LogPolicyScan(_policy(), window_start=100, window_end=200)
        assert scan._get_scan_window() == (100, 200)

    def test_window_derived_from_scan_time_and_period(self):
        scan_time = datetime(2026, 1, 1, 0, 5, 0, tzinfo=timezone.utc)
        scan = LogPolicyScan(_policy(), scan_time=scan_time)
        start, end = scan._get_scan_window()
        assert end == int(scan_time.timestamp())
        assert end - start == 300  # 5 分钟周期


class TestSampleLimitAndGroupBy:
    def test_keyword_sample_limit_default(self):
        assert _scan()._get_keyword_sample_limit({}) == 5

    def test_keyword_sample_limit_parses_str(self):
        assert _scan()._get_keyword_sample_limit({"limit": "12"}) == 12

    def test_keyword_sample_limit_invalid_falls_back(self):
        assert _scan()._get_keyword_sample_limit({"limit": "abc"}) == 5

    def test_keyword_sample_limit_clamped_to_one(self):
        assert _scan()._get_keyword_sample_limit({"limit": 0}) == 1

    def test_normalize_group_by_none(self):
        assert _scan()._normalize_group_by(None) == []

    def test_normalize_group_by_string(self):
        assert _scan()._normalize_group_by("host") == ["host"]

    def test_normalize_group_by_list_filters_empty(self):
        assert _scan()._normalize_group_by(["host", "", "app"]) == ["host", "app"]


class TestParseCountValue:
    def test_parse_int_str(self):
        assert _scan()._parse_count_value("42") == 42

    def test_parse_float_str(self):
        assert _scan()._parse_count_value("42.9") == 42

    def test_parse_none_returns_default(self):
        assert _scan()._parse_count_value(None, default=7) == 7

    def test_parse_empty_returns_default(self):
        assert _scan()._parse_count_value("", default=3) == 3

    def test_parse_invalid_returns_default(self):
        assert _scan()._parse_count_value("xx", default=0) == 0


class TestQueryBuilders:
    def test_build_keyword_group_query(self):
        q = _scan()._build_keyword_group_query("error", ["host", "app"])
        assert q == "error | stats by (host, app) count() as total_count"

    def test_escape_log_query_value(self):
        assert _scan()._escape_log_query_value('a"b\\c') == 'a\\"b\\\\c'

    def test_exact_field_filter_normal(self):
        assert _scan()._build_exact_field_filter("host", "h1") == 'host:="h1"'

    def test_exact_field_filter_stream_braces(self):
        # _stream 且值被花括号包裹时按 stream 选择器原样拼接
        assert _scan()._build_exact_field_filter("_stream", "{a=1}") == "_stream:{a=1}"

    def test_group_sample_query_with_wildcard_base(self):
        q = _scan()._build_group_sample_query("*", {"host": "h1"})
        assert q == 'host:="h1"'

    def test_group_sample_query_with_existing_query(self):
        q = _scan()._build_group_sample_query("error", {"host": "h1"})
        assert q == 'error | filter host:="h1"'

    def test_group_sample_query_no_filters_returns_base(self):
        assert _scan()._build_group_sample_query("error", {}) == "error"


class TestExtractGroupValues:
    def test_complete_values(self):
        result = {"host": "h1", "app": "web"}
        assert _scan()._extract_group_values(result, ["host", "app"]) == result

    def test_missing_value_returns_empty(self):
        assert _scan()._extract_group_values({"host": "h1"}, ["host", "app"]) == {}

    def test_empty_string_value_returns_empty(self):
        assert _scan()._extract_group_values({"host": ""}, ["host"]) == {}


class TestGroupSourceId:
    def test_deterministic_and_prefixed(self):
        scan = _scan(id=9)
        a = scan._build_group_source_id({"host": "h1"})
        b = scan._build_group_source_id({"host": "h1"})
        assert a == b
        assert a.startswith("policy_9_")

    def test_key_order_independent(self):
        scan = _scan()
        a = scan._build_group_source_id({"host": "h1", "app": "x"})
        b = scan._build_group_source_id({"app": "x", "host": "h1"})
        assert a == b


class TestCollectTypeFilter:
    def test_no_collect_type_returns_query_or_star(self):
        assert _scan(collect_type=None)._add_collect_type_filter("") == "*"
        assert _scan(collect_type=None)._add_collect_type_filter("error") == "error"

    def test_wildcard_query_uses_filter_only(self):
        ct = SimpleNamespace(name="nginx")
        assert _scan(collect_type=ct)._add_collect_type_filter("*") == 'collect_type:"nginx"'

    def test_combines_query_and_filter(self):
        ct = SimpleNamespace(name="nginx")
        out = _scan(collect_type=ct)._add_collect_type_filter("error")
        assert out == '(error) AND collect_type:"nginx"'


class TestBuildQueryWithLogGroups:
    def test_no_log_groups_adds_collect_type(self):
        ct = SimpleNamespace(name="nginx")
        out = _scan(collect_type=ct, log_groups=[])._build_query_with_log_groups("error")
        assert out == '(error) AND collect_type:"nginx"'


class TestAggregationQuery:
    def test_count_with_group_by(self):
        rule = {"conditions": [{"func": "count", "field": "_msg"}]}
        q = _scan()._build_aggregation_query("error", ["host"], rule)
        assert q == "error | stats by (host) count() as count__msg"

    def test_sum_avg_max_min_no_group(self):
        rule = {"conditions": [
            {"func": "sum", "field": "bytes"},
            {"func": "avg", "field": "bytes"},
            {"func": "max", "field": "bytes"},
            {"func": "min", "field": "bytes"},
        ]}
        q = _scan()._build_aggregation_query("error", [], rule)
        assert "sum(bytes) as sum_bytes" in q
        assert "avg(bytes) as avg_bytes" in q
        assert q.startswith("error | stats ")

    def test_missing_func_skipped_and_unsupported_ignored(self):
        rule = {"conditions": [{"field": "x"}, {"func": "weird", "field": "y"}]}
        q = _scan()._build_aggregation_query("error", [], rule)
        # 没有有效聚合函数时回退 count() as total_count
        assert q == "error | stats count() as total_count"

    def test_empty_conditions_raises(self):
        with pytest.raises(BaseAppException, match="rule conditions cannot be empty"):
            _scan()._build_aggregation_query("error", [], {"conditions": []})

    def test_dotted_field_alias_sanitized(self):
        rule = {"conditions": [{"func": "count", "field": "log.level"}]}
        q = _scan()._build_aggregation_query("error", [], rule)
        assert "count() as count_log_level" in q


class TestExtractAggregateData:
    def test_count_uses_total_count_fallback(self):
        rule = {"conditions": [{"func": "count", "field": "_msg"}]}
        data = _scan()._extract_aggregate_data({"total_count": "10"}, rule)
        assert data["count"] == 10
        assert data["count__msg"] == 10

    def test_count_invalid_value_defaults_zero(self):
        rule = {"conditions": [{"func": "count", "field": "_msg"}]}
        data = _scan()._extract_aggregate_data({"count__msg": "x"}, rule)
        assert data["count"] == 0

    def test_numeric_funcs_to_float(self):
        rule = {"conditions": [{"func": "avg", "field": "bytes"}]}
        data = _scan()._extract_aggregate_data({"avg_bytes": "3.5"}, rule)
        assert data["avg_bytes"] == 3.5

    def test_numeric_func_invalid_defaults_zero_float(self):
        rule = {"conditions": [{"func": "sum", "field": "bytes"}]}
        data = _scan()._extract_aggregate_data({"sum_bytes": "bad"}, rule)
        assert data["sum_bytes"] == 0.0

    def test_missing_func_skipped(self):
        rule = {"conditions": [{"field": "x"}]}
        assert _scan()._extract_aggregate_data({}, rule) == {}


class TestRenderAlertName:
    def test_default_keyword_when_empty(self):
        assert _scan(alert_name="", alert_type="keyword")._render_alert_name() == "关键字告警"

    def test_default_aggregate_when_empty(self):
        assert _scan(alert_name="", alert_type="aggregate")._render_alert_name() == "聚合告警"

    def test_token_substitution_from_result(self):
        scan = _scan(alert_name="${host} 出错")
        out = scan._render_alert_name({"host": "server01"}, ["host"])
        assert out == "server01 出错"

    def test_missing_token_renders_empty(self):
        scan = _scan(alert_name="${missing} done")
        assert scan._render_alert_name({"host": "h"}, ["host"]) == "done"

    def test_log_prefixed_token(self):
        scan = _scan(alert_name="${log.host}")
        assert scan._render_alert_name({"host": "h1"}, ["host"]) == "h1"

    def test_none_value_renders_empty(self):
        scan = _scan(alert_name="${host}x")
        assert scan._render_alert_name({"host": None}, ["host"]) == "x"


class TestBuildGroupKey:
    def test_empty_group_by(self):
        assert _scan()._build_group_key({}, []) == ""

    def test_scalar_values(self):
        assert _scan()._build_group_key({"host": "h1"}, ["host"]) == "host=h1"

    def test_list_value_joined(self):
        out = _scan()._build_group_key({"tags": ["a", "b"]}, ["tags"])
        assert out == "tags=a,b"

    def test_dict_value_stringified(self):
        out = _scan()._build_group_key({"meta": {"x": 1}}, ["meta"])
        assert "meta=" in out

    def test_none_value_null(self):
        assert _scan()._build_group_key({"host": None}, ["host"]) == "host=null"

    def test_missing_field_unknown(self):
        assert _scan()._build_group_key({}, ["host"]) == "host=unknown"


class TestBuildAggregateSourceId:
    def test_short_unambiguous_group_preserves_legacy_source_id(self):
        scan = _scan(id=9)

        assert scan._build_aggregate_source_id({"host": "h1"}, ["host"]) == "policy_9_host=h1"

    def test_long_group_uses_bounded_hash(self):
        source_id = _scan(id=9)._build_aggregate_source_id({"host": "x" * 200}, ["host"])

        assert source_id.startswith("policy_9_agg_")
        assert len(source_id) <= 100

    def test_legacy_collision_groups_get_distinct_source_ids(self):
        scan = _scan(id=9)
        first = {"a": "x, b=y", "b": "z"}
        second = {"a": "x", "b": "y, b=z"}

        assert scan._build_group_key(first, ["a", "b"]) == scan._build_group_key(second, ["a", "b"])
        assert scan._build_aggregate_source_id(first, ["a", "b"]) != scan._build_aggregate_source_id(
            second, ["a", "b"]
        )

    def test_hashed_identity_is_independent_of_group_field_order(self):
        scan = _scan(id=9)
        result = {"a": "x,y", "b": "z"}

        assert scan._build_aggregate_source_id(result, ["a", "b"]) == scan._build_aggregate_source_id(
            result, ["b", "a"]
        )

    def test_aggregate_detection_uses_bounded_source_id(self, monkeypatch):
        scan = _scan(
            id=9,
            alert_type="aggregate",
            alert_condition={
                "query": "*",
                "group_by": ["host"],
                "rule": {
                    "mode": "and",
                    "conditions": [{"func": "count", "field": "_msg", "op": ">", "value": 2}],
                },
            },
        )
        monkeypatch.setattr(scan.vlogs_api, "query", lambda **_kwargs: [{"host": "x" * 200, "count__msg": "9"}])

        events = scan.aggregate_alert_detection()

        assert events[0]["source_id"].startswith("policy_9_agg_")
        assert len(events[0]["source_id"]) <= 100


class TestCheckRuleConditions:
    def test_no_conditions_false(self):
        assert _scan()._check_rule_conditions({}, {"conditions": []}) is False

    def test_and_mode_all_true(self):
        rule = {"mode": "and", "conditions": [
            {"func": "count", "field": "_msg", "op": ">", "value": 5},
        ]}
        assert _scan()._check_rule_conditions({"count": 10}, rule) is True

    def test_and_mode_one_false(self):
        rule = {"mode": "and", "conditions": [
            {"func": "count", "field": "_msg", "op": ">", "value": 50},
        ]}
        assert _scan()._check_rule_conditions({"count": 10}, rule) is False

    def test_or_mode(self):
        rule = {"mode": "or", "conditions": [
            {"func": "count", "field": "_msg", "op": ">", "value": 50},
            {"func": "sum", "field": "b", "op": ">", "value": 1},
        ]}
        assert _scan()._check_rule_conditions({"count": 1, "sum_b": 5}, rule) is True

    def test_incomplete_condition_skipped_results_empty_false(self):
        rule = {"mode": "and", "conditions": [{"func": "count", "field": "_msg"}]}
        assert _scan()._check_rule_conditions({"count": 1}, rule) is False

    def test_unsupported_mode_false(self):
        rule = {"mode": "xor", "conditions": [
            {"func": "count", "field": "_msg", "op": ">", "value": 0},
        ]}
        assert _scan()._check_rule_conditions({"count": 10}, rule) is False


class TestCompareValues:
    scan = LogPolicyScan(_policy())

    def test_numeric_gt(self):
        assert self.scan._compare_values("10", ">", "5") is True

    def test_numeric_lt(self):
        assert self.scan._compare_values(3, "<", 5) is True

    def test_numeric_eq(self):
        assert self.scan._compare_values(5.0, "=", "5") is True

    def test_numeric_ne(self):
        assert self.scan._compare_values(5, "!=", 6) is True

    def test_numeric_gte(self):
        assert self.scan._compare_values(5, ">=", 5) is True

    def test_numeric_lte(self):
        assert self.scan._compare_values(4, "<=", 5) is True

    def test_in_list(self):
        assert self.scan._compare_values("a", "in", ["a", "b"]) is True

    def test_in_substring(self):
        assert self.scan._compare_values("hello world", "in", "world") is True

    def test_nin_list(self):
        assert self.scan._compare_values("z", "nin", ["a", "b"]) is True

    def test_nin_substring(self):
        assert self.scan._compare_values("hello", "nin", "xyz") is True

    def test_unsupported_op(self):
        assert self.scan._compare_values(1, "~", 1) is False


class TestFormatNoticeContent:
    def test_contains_event_and_policy(self):
        scan = LogPolicyScan(_policy(id=3))
        scan.policy.name = "策略A"
        event = SimpleNamespace(event_time="2026-01-01T00:00:00", content="磁盘满")
        title, content = scan._format_notice_content(event)
        assert title == "【日志告警通知】"
        assert "磁盘满" in content
        assert "策略A" in content
