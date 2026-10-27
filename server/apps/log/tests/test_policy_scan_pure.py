"""apps/log/tasks/services/policy_scan.py 纯逻辑测试。

只测无 DB/IO 的辅助方法：查询构建、聚合解析、条件比较、模板渲染等。
VictoriaMetricsAPI 在 __init__ 中被实例化（不发起连接），其方法在本文件不调用，
因此无需 mock。policy 用 SimpleNamespace 构造，避免 DB。
"""
import logging
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
        # 规格把样本上限收紧到 10；"12" 仍能解析，但读取时钳到上限。
        assert _scan()._get_keyword_sample_limit({"limit": "12"}) == 10

    def test_keyword_sample_limit_caps_at_ten(self):
        assert _scan()._get_keyword_sample_limit({"limit": 50}) == 10

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

    def test_maps_logical_message_to_storage_field(self):
        out = _scan(collect_type=None, log_groups=[])._build_query_with_log_groups('message:"日志类型:本机安全" AND source_ip:10.54.38.109')
        assert out == '_msg:"日志类型:本机安全" AND source_ip:10.54.38.109'

    def test_keeps_physical_msg_filter(self):
        out = _scan(collect_type=None, log_groups=[])._build_query_with_log_groups('_msg:"日志类型:本机安全" AND source_ip:10.54.38.109')
        assert out == '_msg:"日志类型:本机安全" AND source_ip:10.54.38.109'

    def test_maps_message_before_collect_type(self):
        ct = SimpleNamespace(name="syslog")
        out = _scan(collect_type=ct, log_groups=[])._build_query_with_log_groups('message:"error"')
        assert out == '(_msg:"error") AND collect_type:"syslog"'

    def test_completes_empty_message_filter(self):
        out = _scan(collect_type=None, log_groups=[])._build_query_with_log_groups("message:")
        assert out == "_msg:*"

    def test_maps_message_added_by_log_group(self, mocker):
        mocker.patch(
            "apps.log.services.search.LogGroupQueryBuilder.build_query_with_groups",
            return_value=('message:"failed" AND host:*', [{"id": "g1", "name": "g"}]),
        )
        out = _scan(collect_type=None, log_groups=["g1"])._build_query_with_log_groups("*")
        assert out == '_msg:"failed" AND host:*'

    def test_keyword_detection_sends_mapped_message_query(self, mocker):
        scan = _scan(alert_condition={"query": 'message:"error"', "limit": 3})
        query_mock = mocker.patch.object(
            scan.vlogs_api,
            "query",
            side_effect=[[{"_msg": "error A"}], [{"total_count": "1"}]],
        )

        events = scan.keyword_alert_detection()

        assert events
        assert query_mock.call_args_list[0].kwargs["query"] == '_msg:"error"'
        assert query_mock.call_args_list[1].kwargs["query"] == '_msg:"error" | stats count() as total_count'
        assert events[0]["raw_data"] == [{"message": "error A"}]
        assert events[0]["jump_query"]["query"] == '_msg:"error"'
        assert events[0]["jump_query"]["window_start"] < events[0]["jump_query"]["window_end"]


class TestAggregationQuery:
    def test_count_with_group_by(self):
        rule = {"conditions": [{"func": "count", "field": "_msg"}]}
        q = _scan()._build_aggregation_query("error", ["host"], rule)
        assert q == "error | stats by (host) count() as count__msg"

    def test_sum_avg_max_min_no_group(self):
        rule = {
            "conditions": [
                {"func": "sum", "field": "bytes"},
                {"func": "avg", "field": "bytes"},
                {"func": "max", "field": "bytes"},
                {"func": "min", "field": "bytes"},
            ]
        }
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

    def test_count_rate_and_delta_share_one_count_alias(self):
        rule = {
            "conditions": [
                {"func": "count", "field": "_msg"},
                {"func": "count_rate", "field": "_msg"},
                {"func": "count_delta", "field": "_msg"},
            ]
        }
        q = _scan()._build_aggregation_query("level:error", ["service"], rule)
        assert q.count("count() as count__msg") == 1
        assert "count_rate" not in q
        assert "count_delta" not in q


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

    def test_aggregate_tokens_render_rate_with_two_decimals(self):
        scan = _scan(alert_name="${count_rate} ${count_delta} ${previous_count}")
        rendered = scan._render_alert_name(
            {"service": "order"},
            ["service"],
            aggregate_data={"count_rate": 0.6, "count_delta": 130, "previous_count": 50},
        )
        assert rendered == "0.60 130 50"


class TestCheckRuleConditions:
    def test_no_conditions_false(self):
        assert _scan()._check_rule_conditions({}, {"conditions": []}) is False

    def test_and_mode_all_true(self):
        rule = {
            "mode": "and",
            "conditions": [
                {"func": "count", "field": "_msg", "op": ">", "value": 5},
            ],
        }
        assert _scan()._check_rule_conditions({"count": 10}, rule) is True

    def test_and_mode_one_false(self):
        rule = {
            "mode": "and",
            "conditions": [
                {"func": "count", "field": "_msg", "op": ">", "value": 50},
            ],
        }
        assert _scan()._check_rule_conditions({"count": 10}, rule) is False

    def test_or_mode(self):
        rule = {
            "mode": "or",
            "conditions": [
                {"func": "count", "field": "_msg", "op": ">", "value": 50},
                {"func": "sum", "field": "b", "op": ">", "value": 1},
            ],
        }
        assert _scan()._check_rule_conditions({"count": 1, "sum_b": 5}, rule) is True

    def test_incomplete_condition_skipped_results_empty_false(self):
        rule = {"mode": "and", "conditions": [{"func": "count", "field": "_msg"}]}
        assert _scan()._check_rule_conditions({"count": 1}, rule) is False

    def test_unsupported_mode_false(self):
        rule = {
            "mode": "xor",
            "conditions": [
                {"func": "count", "field": "_msg", "op": ">", "value": 0},
            ],
        }
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


class TestDerivedAggregateMath:
    def _rule(self, *conditions, mode="and"):
        return {"mode": mode, "conditions": list(conditions)}

    def test_count_rate_and_delta_use_window_and_previous(self):
        rule = self._rule(
            {"func": "count_rate", "field": "_msg", "op": ">", "value": "0.5"},
            {"func": "count_delta", "field": "_msg", "op": ">", "value": "50"},
        )
        data = _scan()._extract_aggregate_data(
            {"service": "order", "count__msg": "180"},
            rule,
            window_seconds=300,
            previous_counts={("order",): 50},
            group_by=["service"],
        )
        assert data["count"] == 180
        assert data["count__msg"] == 180
        assert data["count_rate"] == pytest.approx(0.6)
        assert data["previous_count"] == 50
        assert data["count_delta"] == 130
        assert data["window_seconds"] == 300
        assert _scan()._check_rule_conditions(data, rule) is True

    def test_missing_previous_group_counts_as_zero(self):
        rule = self._rule({"func": "count_delta", "field": "_msg", "op": ">", "value": "50"})
        data = _scan()._extract_aggregate_data(
            {"service": "cart", "count__msg": "100"},
            rule,
            window_seconds=300,
            previous_counts={("pay",): 90},
            group_by=["service"],
        )
        assert data["previous_count"] == 0
        assert data["count_delta"] == 100
        assert _scan()._check_rule_conditions(data, rule) is True

    def test_unavailable_previous_window_blocks_delta_but_or_can_still_trigger(self):
        scan = _scan()
        rate_and_delta = self._rule(
            {"func": "count_delta", "field": "_msg", "op": ">", "value": "50"},
            {"func": "count", "field": "_msg", "op": ">", "value": "10"},
            mode="and",
        )
        blocked = scan._extract_aggregate_data(
            {"count__msg": "180"},
            rate_and_delta,
            window_seconds=300,
            previous_counts=None,
            group_by=[],
        )
        assert blocked["count_delta"] is None
        assert blocked["previous_count"] is None
        assert scan._check_rule_conditions(blocked, rate_and_delta) is False

        either = self._rule(
            {"func": "count_delta", "field": "_msg", "op": ">", "value": "50"},
            {"func": "count", "field": "_msg", "op": ">", "value": "10"},
            mode="or",
        )
        opened = scan._extract_aggregate_data(
            {"count__msg": "180"},
            either,
            window_seconds=300,
            previous_counts=None,
            group_by=[],
        )
        assert scan._check_rule_conditions(opened, either) is True

    def test_negative_delta_threshold_triggers_drop(self):
        rule = self._rule({"func": "count_delta", "field": "_msg", "op": "<", "value": "-100"})
        data = _scan()._extract_aggregate_data(
            {"count__msg": "10"},
            rule,
            window_seconds=300,
            previous_counts={(): 200},
            group_by=[],
        )
        assert data["count_delta"] == -190
        assert _scan()._check_rule_conditions(data, rule) is True

    def test_previous_window_failure_returns_none_without_query_text(self):
        sentinel = "SENTINEL_QUERY_BODY_level:error_do_not_log"
        scan = _scan(id=42)
        scan.vlogs_api.query = lambda **kwargs: (_ for _ in ()).throw(RuntimeError(sentinel))
        template = "event=log_policy_previous_window_failed policy_id=%s failed_stage=%s error_type=%s"
        records = []

        class _Capture(logging.Handler):
            def emit(self, record):
                records.append(record)

        handler = _Capture(level=logging.WARNING)
        logger = logging.getLogger("celery")
        previous_level = logger.level
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
        try:
            result = scan._query_previous_window_counts(sentinel, ["service"], 1000, 1300)
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous_level)

        assert result is None
        matched = [record for record in records if record.msg == template]
        assert len(matched) == 1
        record = matched[0]
        assert record.args == (42, "previous_window", "RuntimeError")
        assert record.exc_info in (None, False)
        rendered = record.getMessage()
        assert rendered == "event=log_policy_previous_window_failed policy_id=42 failed_stage=previous_window error_type=RuntimeError"
        assert sentinel not in rendered
        assert sentinel not in str(record.args)

    def test_evaluate_aggregate_queries_previous_window_only_for_delta(self, mocker):
        count_only = _scan(
            alert_type="aggregate",
            alert_condition={
                "query": "level:error",
                "group_by": ["service"],
                "rule": {"mode": "and", "conditions": [{"func": "count", "field": "_msg", "op": ">", "value": "1"}]},
            },
        )
        query = mocker.patch.object(count_only.vlogs_api, "query", return_value=[{"service": "order", "count__msg": "3"}])
        rows = count_only.evaluate_aggregate(1000, 1300)
        assert query.call_count == 1
        assert rows[0]["triggered"] is True
        assert "count_delta" not in rows[0]["aggregate_data"]
        assert count_only.baseline_status == "not_required"

        delta = _scan(
            alert_type="aggregate",
            alert_condition={
                "query": "level:error",
                "group_by": ["service"],
                "rule": {
                    "mode": "and",
                    "conditions": [
                        {"func": "count_rate", "field": "_msg", "op": ">", "value": "0.5"},
                        {"func": "count_delta", "field": "_msg", "op": ">", "value": "50"},
                    ],
                },
            },
        )

        def fake_query(query, start, end, limit=10):
            if start == 1000:
                raise RuntimeError("previous down")
            return [{"service": "order", "count__msg": "180"}, {"service": "pay", "count__msg": "100"}]

        mocker.patch.object(delta.vlogs_api, "query", side_effect=fake_query)
        failed_rows = delta.evaluate_aggregate(1300, 1600)
        assert delta.baseline_status == "unavailable"
        assert all(row["triggered"] is False and row["reason"] == "missing_baseline" for row in failed_rows)

        def fake_ok(query, start, end, limit=10):
            if start == 1000:
                return [{"service": "order", "count__msg": "50"}, {"service": "pay", "count__msg": "90"}]
            return [{"service": "order", "count__msg": "180"}, {"service": "pay", "count__msg": "100"}]

        mocker.patch.object(delta.vlogs_api, "query", side_effect=fake_ok)
        ok_rows = {row["group_values"]["service"]: row for row in delta.evaluate_aggregate(1300, 1600)}
        assert ok_rows["order"]["triggered"] is True
        assert ok_rows["order"]["aggregate_data"]["count_rate"] == pytest.approx(0.6)
        assert ok_rows["order"]["aggregate_data"]["count_delta"] == 130
        assert ok_rows["pay"]["triggered"] is False
        assert ok_rows["pay"]["reason"] == ""


class TestFormatNoticeContent:
    def test_contains_event_and_policy(self):
        from apps.log.constants.web import WebConstants

        scan = LogPolicyScan(_policy(id=3))
        scan.policy.name = "策略A"
        event = SimpleNamespace(event_time="2026-01-01T00:00:00", content="磁盘满")
        title, content = scan._format_notice_content(event)
        assert title == "【日志告警通知】"
        assert content == "\n".join(
            [
                "时间：2026-01-01T00:00:00",
                "告警内容：磁盘满",
                "策略名称：策略A",
                f'查看告警详情：<a href="{WebConstants.URL}/log/event/alert">点击查看详情</a>',
            ]
        )
        assert "命中条数" not in content
        assert "样本" not in content

    def test_aggregate_notice_adds_hit_window_samples_and_search(self):
        from apps.log.constants.web import WebConstants

        scan = LogPolicyScan(_policy(id=3, name="策略A", log_groups=["g1"]))
        long_message = "m" * 210
        event = SimpleNamespace(
            event_time="2026-10-27T07:50:00Z",
            content="order 告警",
            raw_data={
                "aggregate_result": {"count": 180, "count_rate": 0.6, "count_delta": 130},
                "samples": [{"message": long_message}, {"_msg": "second\nline"}, {"message": ""}],
                "jump_query": {"query": "level:error", "window_start": 1700000000, "window_end": 1700000300},
            },
        )
        title, content = scan._format_notice_content(event)
        assert title == "【日志告警通知】"
        assert "命中条数：180（速率 0.60 条/秒，较上一窗 +130）" in content
        assert "检测窗口：2023-11-14 22:13:20 ~ 22:18:20" in content
        assert f"  - {'m' * 200}…" in content
        assert "  - second line" in content
        assert content.count("  - ") == 2
        assert f"{WebConstants.URL}/log/search?" in content
        assert "startTime=1700000000000" in content
        assert "endTime=1700000300000" in content
        assert "log_groups=g1" in content
        assert f"{WebConstants.URL}/log/event/alert" in content


class TestJumpQueryAndAggregateSamples:
    def test_jump_query_uses_and_exact_filter(self):
        scan = _scan()
        jump = scan._build_jump_query("level:error", {"service": 'ord"er'}, 100, 400)
        assert jump == {
            "query": 'level:error AND service:="ord\\"er"',
            "window_start": 100,
            "window_end": 400,
        }

    def test_aggregate_samples_are_capped_and_failure_keeps_event(self, mocker, caplog):
        scan = LogPolicyScan(
            _policy(
                alert_type="aggregate",
                alert_name="hit",
                alert_condition={
                    "query": "level:error",
                    "group_by": ["service"],
                    "limit": 50,
                    "rule": {"mode": "and", "conditions": [{"func": "count", "field": "_msg", "op": ">", "value": 1}]},
                },
            ),
            window_start=100,
            window_end=400,
        )
        secret = "SENTINEL_SAMPLE_QUERY"

        def succeed(query, start, end, limit=10):
            if "stats" in query:
                return [{"service": "order", "count__msg": "9"}]
            assert limit == 10
            return [{"_msg": f"m{index}"} for index in range(12)]

        mocker.patch.object(scan.vlogs_api, "query", side_effect=succeed)
        events = scan.aggregate_alert_detection()
        assert len(events) == 1
        assert len(events[0]["raw_data"]["samples"]) == 10
        assert events[0]["raw_data"]["samples"][0]["message"] == "m0"
        assert events[0]["jump_query"]["window_start"] == 100
        assert events[0]["jump_query"]["window_end"] == 400
        assert events[0]["jump_query"]["query"] == 'level:error AND service:="order"'
        assert events[0]["raw_data"]["jump_query"] == events[0]["jump_query"]

        def fail(query, start, end, limit=10):
            if "stats" in query:
                return [{"service": "order", "count__msg": "9"}]
            raise RuntimeError(secret)

        mocker.patch.object(scan.vlogs_api, "query", side_effect=fail)
        with caplog.at_level(logging.WARNING, logger="celery"):
            failed = scan.aggregate_alert_detection()
        assert len(failed) == 1
        assert failed[0]["raw_data"]["samples"] == []
        warnings = [record for record in caplog.records if record.levelno == logging.WARNING and "aggregate_sample_failed" in record.getMessage()]
        assert warnings
        assert secret not in warnings[-1].getMessage()
