"""CMDB 查询条件格式化覆盖测试。

对照 specs/capabilities/legacy-prd-cmdb-搜索.md：查询参数按类型(str/int/list/id/time/bool)编译为 Cypher 条件片段。
"""

import pytest

from apps.cmdb.graph import format_type as ft


# --------------------------------------------------------------------------
# 直接拼接版本（FORMAT_TYPE）
# --------------------------------------------------------------------------


def test_format_bool():
    assert ft.format_bool({"field": "active", "value": True}) == "n.active = True"


def test_format_time():
    out = ft.format_time({"field": "ts", "start": "2026-01-01", "end": "2026-01-02"})
    assert "n.ts >= '2026-01-01'" in out and "n.ts <= '2026-01-02'" in out


def test_format_str_eq_neq():
    assert ft.format_str_eq({"field": "name", "value": "host"}) == "n.name = 'host'"
    assert ft.format_str_neq({"field": "name", "value": "host"}) == "n.name <> 'host'"


def test_format_str_contains_like():
    assert ft.format_str_contains({"field": "name", "value": "h"}) == "n.name =~ '.*h.*'"
    assert ft.format_str_like({"field": "name", "value": "h"}) == "n.name contains 'h'"


def test_format_str_in_user_in():
    assert ft.format_str_in({"field": "name", "value": ["a", "b"]}) == "n.name IN ['a', 'b']"
    assert ft.format_user_in({"field": "owner", "value": ["u"]}) == "n.owner IN ['u']"


def test_format_int_ops():
    assert ft.format_int_eq({"field": "c", "value": 1}) == "n.c = 1"
    assert ft.format_int_gt({"field": "c", "value": 1}) == "n.c > 1"
    assert ft.format_int_lt({"field": "c", "value": 1}) == "n.c < 1"
    assert ft.format_int_neq({"field": "c", "value": 1}) == "n.c <> 1"
    assert ft.format_int_in({"field": "c", "value": [1, 2]}) == "n.c IN [1, 2]"


def test_format_list_in():
    assert ft.format_list_in({"field": "tags", "value": [2, 5]}) == "(2 IN n.tags AND 5 IN n.tags)"
    assert ft.format_list_in({"field": "tags", "value": []}) == "false"
    assert ft.format_list_in({"field": "tags", "value": "bad"}) == "false"


def test_format_list_any():
    assert ft.format_list_any({"field": "tags", "value": [2, 5]}) == "(2 IN n.tags OR 5 IN n.tags)"
    assert ft.format_list_any({"field": "tags", "value": []}) == "false"


def test_format_list_none():
    assert ft.format_list_none({"field": "tags", "value": ["a", "b"]}) == "(NOT ('a' IN n.tags) AND NOT ('b' IN n.tags))"
    collector = ft.ParameterCollector()
    assert ft.format_list_none_params({"field": "tags", "value": ["a"]}, collector).startswith("NONE(")


def test_format_id_eq_in():
    assert ft.format_id_eq({"value": 115}) == "ID(n) = 115"
    assert ft.format_id_in({"value": [115, 116]}) == "ID(n) IN [115, 116]"
    assert ft.id_eq({"value": 1}) == "id(n) = 1"
    assert ft.id_in({"value": [1, 2]}) == "id(n) IN [1, 2]"


def test_compile_tag_exact_match_query():
    assert ft.compile_tag_exact_match_query("tags", []) == []
    out = ft.compile_tag_exact_match_query("tags", ["a", "b"])
    assert out and out[0]["field"] == "tags"


def test_format_type_map_complete():
    expected = {"bool", "time", "str=", "str<>", "str*", "str[]", "user[]",
                "int=", "int>", "int<", "int<>", "int[]", "id=", "id[]", "list[]", "list_any[]", "list_none[]"}
    assert expected <= set(ft.FORMAT_TYPE.keys())


# --------------------------------------------------------------------------
# 参数化版本（FORMAT_TYPE_PARAMS）
# --------------------------------------------------------------------------


def test_parameter_collector():
    c = ft.ParameterCollector()
    p1 = c.add_param("v1")
    p2 = c.add_param("v2", prefix="x")
    assert p1 == "$p1"
    assert p2 == "$x2"
    assert c.get_params() == {"p1": "v1", "x2": "v2"}
    c.reset()
    assert c.get_params() == {}


def test_format_str_eq_params():
    c = ft.ParameterCollector()
    out = ft.format_str_eq_params({"field": "name", "value": "host"}, c)
    assert out.startswith("n.name = $")
    assert "host" in c.get_params().values()


def test_format_int_eq_params():
    c = ft.ParameterCollector()
    out = ft.format_int_eq_params({"field": "c", "value": 5}, c)
    assert "n.c = $" in out
    assert 5 in c.get_params().values()


def test_format_list_in_params():
    c = ft.ParameterCollector()
    out = ft.format_list_in_params({"field": "tags", "value": [1, 2]}, c)
    assert "n.tags" in out


def test_format_id_eq_params():
    c = ft.ParameterCollector()
    out = ft.format_id_eq_params({"value": 5}, c)
    assert "ID(n) = $" in out


def test_format_type_params_map_complete():
    assert set(ft.FORMAT_TYPE_PARAMS.keys()) == set(ft.FORMAT_TYPE.keys())
