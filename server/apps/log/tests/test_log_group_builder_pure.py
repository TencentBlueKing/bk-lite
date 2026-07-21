import pydantic.root_model  # noqa

from types import SimpleNamespace

import pytest

from apps.log.utils.log_group import LogGroupQueryBuilder


def _group(gid, name="g", rule=None):
    return SimpleNamespace(id=gid, name=name, rule=rule)


# ----------------------- json_to_logsql_expression -----------------------


def test_json_to_logsql_empty_rule_returns_empty():
    assert LogGroupQueryBuilder.json_to_logsql_expression(None) == ""
    assert LogGroupQueryBuilder.json_to_logsql_expression({}) == ""


def test_json_to_logsql_single_eq_condition():
    rule = {"conditions": [{"field": "level", "op": "==", "value": "error"}]}
    assert LogGroupQueryBuilder.json_to_logsql_expression(rule) == 'level:"error"'


def test_json_to_logsql_multiple_and():
    rule = {
        "mode": "and",
        "conditions": [
            {"field": "level", "op": "==", "value": "error"},
            {"field": "host", "op": "!=", "value": "web"},
        ],
    }
    assert LogGroupQueryBuilder.json_to_logsql_expression(rule) == '(level:"error" AND !host:"web")'


def test_json_to_logsql_or_mode():
    rule = {
        "mode": "OR",
        "conditions": [
            {"field": "a", "op": "startswith", "value": "x"},
            {"field": "b", "op": "endswith", "value": "y"},
        ],
    }
    assert LogGroupQueryBuilder.json_to_logsql_expression(rule) == "(a:x* OR b:*y)"


def test_json_to_logsql_unknown_mode_raises():
    rule = {
        "mode": "ADN",
        "conditions": [
            {"field": "a", "op": "==", "value": "x"},
            {"field": "b", "op": "==", "value": "y"},
        ],
    }

    with pytest.raises(ValueError, match="Unsupported mode"):
        LogGroupQueryBuilder.json_to_logsql_expression(rule)


def test_json_to_logsql_contains_escapes_regex():
    rule = {"conditions": [{"field": "msg", "op": "contains", "value": "a.b"}]}
    out = LogGroupQueryBuilder.json_to_logsql_expression(rule)
    assert out == 'msg:re(".*a\\.b.*")'


def test_json_to_logsql_not_contains():
    rule = {"conditions": [{"field": "msg", "op": "!contains", "value": "x"}]}
    assert LogGroupQueryBuilder.json_to_logsql_expression(rule) == '!msg:re(".*x.*")'


def test_json_to_logsql_unsupported_op_raises():
    rule = {"conditions": [{"field": "f", "op": "~~", "value": "v"}]}
    with pytest.raises(ValueError, match="Unsupported operation"):
        LogGroupQueryBuilder.json_to_logsql_expression(rule)


def test_json_to_logsql_no_conditions_returns_empty():
    assert LogGroupQueryBuilder.json_to_logsql_expression({"conditions": []}) == ""


# ----------------------- build_query_with_groups (resolved_groups path) -----------------------


def test_build_query_no_group_ids_returns_user_query():
    out, info = LogGroupQueryBuilder.build_query_with_groups("level:error", [])
    assert out == "level:error"
    assert info == []


def test_build_query_no_valid_groups_denies_all():
    out, info = LogGroupQueryBuilder.build_query_with_groups("q", ["g1"], resolved_groups=[])
    assert out == LogGroupQueryBuilder.DENY_ALL_QUERY
    assert info == []


def test_build_query_with_default_keeps_user_query():
    g = _group("g1", rule={"conditions": [{"field": "level", "op": "==", "value": "error"}]})
    out, info = LogGroupQueryBuilder.build_query_with_groups("host:web", ["default", "g1"], resolved_groups=[g])
    assert out == "host:web"
    # default 注入到 group_info 头部
    assert info[0]["id"] == "default"


def test_build_query_with_default_and_empty_user_query_returns_star():
    g = _group("g1", rule=None)
    out, _ = LogGroupQueryBuilder.build_query_with_groups("", ["default", "g1"], resolved_groups=[g])
    assert out == "*"


def test_build_query_combines_user_and_group_filter():
    g = _group("g1", rule={"conditions": [{"field": "level", "op": "==", "value": "error"}]})
    out, info = LogGroupQueryBuilder.build_query_with_groups("host:web", ["g1"], resolved_groups=[g])
    assert out == '(host:web) AND (level:"error")'
    assert info[0]["status"] == "applied"


def test_build_query_all_empty_rule_groups_returns_user_query():
    g = _group("g1", rule=None)
    out, info = LogGroupQueryBuilder.build_query_with_groups("host:web", ["g1"], resolved_groups=[g])
    assert out == "host:web"
    assert info[0]["status"] == "empty_rule"


def test_build_query_invalid_rule_marks_status_and_denies():
    # rule 触发 json_to_logsql 抛错（不支持的 op）-> invalid_rule -> 无有效条件 -> DENY_ALL
    g = _group("g1", rule={"conditions": [{"field": "f", "op": "??", "value": "v"}]})
    out, info = LogGroupQueryBuilder.build_query_with_groups("host:web", ["g1"], resolved_groups=[g])
    assert out == LogGroupQueryBuilder.DENY_ALL_QUERY
    assert info[0]["status"] == "invalid_rule"


def test_build_query_unknown_mode_marks_status_and_denies():
    g = _group(
        "g1",
        rule={
            "mode": "ADN",
            "conditions": [
                {"field": "a", "op": "==", "value": "x"},
                {"field": "b", "op": "==", "value": "y"},
            ],
        },
    )

    out, info = LogGroupQueryBuilder.build_query_with_groups("host:web", ["g1"], resolved_groups=[g])

    assert out == LogGroupQueryBuilder.DENY_ALL_QUERY
    assert info[0]["status"] == "invalid_rule"


def test_build_query_multiple_groups_uses_or_filter():
    g1 = _group("g1", rule={"conditions": [{"field": "level", "op": "==", "value": "error"}]})
    g2 = _group("g2", rule={"conditions": [{"field": "level", "op": "==", "value": "warn"}]})
    out, _ = LogGroupQueryBuilder.build_query_with_groups("host:web", ["g1", "g2"], resolved_groups=[g1, g2])
    assert out == '(host:web) AND ((level:"error" OR level:"warn"))'


# ----------------------- _combine_query_and_groups aggregation branch -----------------------


def test_combine_query_aggregation_merges_filter_part():
    out = LogGroupQueryBuilder._combine_query_and_groups(
        "level:error | stats count()", ['host:"web"']
    )
    assert out == '(level:error) AND (host:"web") | stats count()'


def test_combine_query_aggregation_no_filter_part():
    out = LogGroupQueryBuilder._combine_query_and_groups("| stats count()", ['host:"web"'])
    assert out == 'host:"web" | stats count()'


def test_combine_query_no_group_conditions_denies():
    assert LogGroupQueryBuilder._combine_query_and_groups("x", []) == LogGroupQueryBuilder.DENY_ALL_QUERY


def test_combine_query_group_filter_only_when_user_query_empty():
    assert LogGroupQueryBuilder._combine_query_and_groups("", ['host:"web"']) == 'host:"web"'


# ----------------------- validate_log_groups -----------------------


def test_validate_log_groups_empty_is_valid():
    assert LogGroupQueryBuilder.validate_log_groups([]) == (True, "", [])


def test_validate_log_groups_non_list():
    ok, msg, groups = LogGroupQueryBuilder.validate_log_groups("g1")
    assert ok is False
    assert "数组" in msg


def test_validate_log_groups_only_default_is_valid():
    assert LogGroupQueryBuilder.validate_log_groups(["default"]) == (True, "", [])


def test_validate_log_groups_all_exist(mocker):
    existing = [_group("g1"), _group("g2")]
    mocker.patch(
        "apps.log.utils.log_group.LogGroup.objects.filter",
        return_value=existing,
    )
    ok, msg, groups = LogGroupQueryBuilder.validate_log_groups(["g1", "g2"])
    assert ok is True and msg == ""
    assert {g.id for g in groups} == {"g1", "g2"}


def test_validate_log_groups_missing_reported(mocker):
    existing = [_group("g1")]
    mocker.patch(
        "apps.log.utils.log_group.LogGroup.objects.filter",
        return_value=existing,
    )
    ok, msg, groups = LogGroupQueryBuilder.validate_log_groups(["g1", "g2"])
    assert ok is False
    assert "g2" in msg


def test_validate_log_groups_db_error(mocker):
    mocker.patch(
        "apps.log.utils.log_group.LogGroup.objects.filter",
        side_effect=RuntimeError("db down"),
    )
    ok, msg, groups = LogGroupQueryBuilder.validate_log_groups(["g1"])
    assert ok is False
    assert "db down" in msg
    assert groups == []
