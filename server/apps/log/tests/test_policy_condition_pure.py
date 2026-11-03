"""条件归一、别名与 stats 片段。不访问数据库。"""

from apps.log.services.policy_condition import collect_stats_expressions, condition_alias, normalize_condition, stats_expression
from apps.log.services.search import SearchService


def test_normalize_count_delta_to_count_delta_previous_window():
    normalized = normalize_condition({"func": "count_delta", "field": "host", "op": ">", "value": "50"})
    assert normalized["func"] == "count"
    assert normalized["field"] == "_msg"
    assert normalized["op"] == ">"
    assert normalized["value"] == "50"
    assert normalized["compare"] == {"kind": "delta", "to": "previous_window"}
    assert normalized["params"] == {}


def test_normalize_defaults_absolute_compare_and_params():
    normalized = normalize_condition({"func": "count", "field": "_msg", "op": ">", "value": "1"})
    assert normalized["compare"] == {"kind": "absolute"}
    assert normalized["params"] == {}


def test_condition_alias_quantile_ratio_and_dotted_uniq():
    assert condition_alias({"func": "quantile", "field": "duration", "params": {"quantile": 0.95}}) == "quantile_0_95_duration"
    assert condition_alias({"func": "ratio", "field": "_msg", "params": {"filter": "status:500"}}, 0) == "ratio_0"
    assert condition_alias({"func": "ratio", "params": {"filter": "status:500"}}, 2) == "ratio_2"
    assert condition_alias({"func": "count_uniq", "field": "client.ip"}) == "count_uniq_client_ip"


def test_stats_expressions_dedup_message_count():
    conditions = [
        {"func": "count", "field": "_msg"},
        {"func": "count_rate", "field": "_msg"},
        {"func": "count_delta", "field": "host"},
    ]
    expressions = collect_stats_expressions(conditions, None)
    assert expressions == ["count() as count__msg"]


def test_stats_expression_new_funcs():
    assert stats_expression({"func": "count_uniq", "field": "host"}, 0, None) == "count_uniq(host) limit 1000000 as count_uniq_host"
    assert (
        stats_expression({"func": "quantile", "field": "duration", "params": {"quantile": 0.95}}, 0, None)
        == "quantile(0.95, duration) as quantile_0_95_duration"
    )
    assert stats_expression({"func": "bytes_rate", "field": "_msg"}, 0, None) == "sum_len(_msg) as bytes__msg"


def test_ratio_filter_maps_message_and_wraps_parentheses():
    def mapper(text):
        return SearchService._build_storage_query(text, None)[0]

    expression = stats_expression(
        {"func": "ratio", "field": "_msg", "params": {"filter": 'message:"error"'}},
        1,
        mapper,
    )
    assert expression == 'count() if ((_msg:"error")) as ratio_1_hit'
    expressions = collect_stats_expressions(
        [
            {"func": "count_rate", "field": "_msg"},
            {"func": "ratio", "field": "_msg", "params": {"filter": 'message:"error"'}},
        ],
        mapper,
    )
    assert expressions.count("count() as count__msg") == 1
    assert 'count() if ((_msg:"error")) as ratio_1_hit' in expressions
