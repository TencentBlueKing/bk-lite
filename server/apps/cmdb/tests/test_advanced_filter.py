"""关联筛选的格式化、校验和编译。"""

import pytest

from apps.cmdb.graph.advanced_filter import AdvancedFilterError, compile_advanced_filter, resolve_advanced_filter
from apps.cmdb.graph.falkordb import FalkorDBClient
from apps.cmdb.graph.format_type import (
    ParameterCollector,
    apply_node_alias,
    format_empty_params,
    format_str_eq_params,
    format_str_not_like_params,
    format_time_before_params,
)

ASSOCIATIONS = {
    "mysql_run_host": {"src_model_id": "mysql", "dst_model_id": "host"},
    "host_belong_cluster": {"src_model_id": "host", "dst_model_id": "cluster"},
    "mysql_connect_host": {"src_model_id": "mysql", "dst_model_id": "host"},
    "app_connect_app": {"src_model_id": "application", "dst_model_id": "application"},
}
VISIBLE = {"mysql", "host", "cluster"}
ATTRS = {
    "mysql": {"version": "str"},
    "host": {"os_type": "str", "ip_addr": "str"},
    "cluster": {"env": "enum"},
}


def _resolve(payload):
    return resolve_advanced_filter("mysql", payload, ASSOCIATIONS, VISIBLE, ATTRS)


def _compile(payload, permission_for=None):
    logic, resolved = _resolve(payload)
    collector = ParameterCollector()
    match = compile_advanced_filter(
        "mysql",
        logic,
        resolved,
        label="instance",
        collector=collector,
        permission_for=permission_for,
        base_params=[{"field": "model_id", "type": "str=", "value": "mysql"}],
    )
    return match, collector.get_params()


def test_default_alias_keeps_node_name_and_new_operators_are_parameterized():
    collector = ParameterCollector()
    assert format_str_eq_params({"field": "name", "value": "db"}, collector) == "n.name = $str1"
    assert format_str_not_like_params({"field": "name", "value": "8.0", "case_sensitive": True}, collector) == "NOT (n.name CONTAINS $str2)"
    assert format_time_before_params({"field": "created", "value": "2026-01-01"}, collector) == "n.created < $time3"
    assert format_empty_params({"field": "os_type"}, collector) == "(n.os_type IS NULL OR n.os_type = '' OR n.os_type = [])"
    renamed = apply_node_alias("n.name CONTAINS $str1 AND NONE(x IN $list1 WHERE x IN n.tags) AND ID(n) = $id1", "h0")
    assert renamed == "h0.name CONTAINS $str1 AND NONE(x IN $list1 WHERE x IN h0.tags) AND ID(h0) = $id1"


def test_format_search_params_alias_changes_only_the_node():
    client = FalkorDBClient()
    text, params = client.format_search_params([{"field": "os_type", "type": "str=", "value": "linux"}], alias="h0")
    assert text == "(h0.os_type = $str1)"
    assert params == {"str1": "linux"}
    unchanged, _ = client.format_search_params([{"field": "os_type", "type": "str=", "value": "linux"}])
    assert unchanged == "(n.os_type = $str1)"


def test_and_binds_same_first_hop_and_checks_permission_only_on_conditioned_nodes():
    seen = []

    def permission_for(model_id, alias):
        seen.append((model_id, alias))
        return f"{alias}.org = $perm"

    match, _ = _compile(
        {
            "logic": "AND",
            "conditions": [
                {"path": ["mysql_run_host"], "field": "os_type", "type": "str=", "value": "linux"},
                {"path": ["mysql_run_host", "host_belong_cluster"], "field": "env", "type": "list_any[]", "value": ["prod"]},
                {"path": ["mysql_connect_host"], "field": "os_type", "type": "str=", "value": "windows"},
            ],
        },
        permission_for,
    )
    assert match.count("WITH DISTINCT n") == 2
    assert "MATCH (n)-[r0a]-(h0:instance)" in match
    assert "MATCH (h0)-[r0_0]-(e0_0:instance)" in match
    assert "MATCH (n)-[r1a]-(h1:instance)" in match
    assert ("host", "h0") in seen
    assert ("cluster", "e0_0") in seen
    assert ("host", "h1") in seen
    assert "h0.org = $perm" in match
    assert "e0_0.org = $perm" in match


def test_two_hop_without_intermediate_condition_does_not_filter_the_middle_node():
    def permission_for(model_id, alias):
        return f"{alias}.org = $perm"

    match, _ = _compile(
        {
            "logic": "AND",
            "conditions": [
                {"path": ["mysql_run_host", "host_belong_cluster"], "field": "env", "type": "list_any[]", "value": ["prod"]},
            ],
        },
        permission_for,
    )
    assert "h0.org" not in match
    assert "e0_0.org = $perm" in match


def test_or_uses_optional_match_for_each_full_path():
    match, _ = _compile(
        {
            "logic": "OR",
            "conditions": [
                {"path": [], "field": "version", "type": "str*", "value": "8.0"},
                {"path": ["mysql_run_host"], "field": "os_type", "type": "str=", "value": "linux"},
            ],
        }
    )
    assert "OPTIONAL MATCH (n)-[q1]-(x1:instance)" in match
    assert "WHERE c0 OR c1" in match
    assert "WITH DISTINCT n" not in match


@pytest.mark.parametrize(
    ("payload", "index", "message"),
    [
        ({"logic": "AND", "conditions": [{"path": ["missing"], "field": "os_type", "type": "str=", "value": "linux"}]}, 1, "关联关系不存在"),
        (
            {
                "logic": "AND",
                "conditions": [{"path": ["mysql_run_host", "mysql_run_host"], "field": "os_type", "type": "str=", "value": "linux"}],
            },
            1,
            "不能沿同一关系返回",
        ),
        ({"logic": "AND", "conditions": [{"path": ["a", "b", "c"], "field": "os_type", "type": "str=", "value": "linux"}]}, 1, "关联路径最多两层"),
        (
            {
                "logic": "AND",
                "conditions": [{"path": ["mysql_run_host", "app_connect_app"], "field": "os_type", "type": "str=", "value": "linux"}],
            },
            1,
            "关联关系与上一步不相接",
        ),
        ({"logic": "AND", "conditions": [{"path": ["mysql_run_host"], "field": "missing", "type": "str=", "value": "linux"}]}, 1, "字段不可筛选"),
        ({"logic": "AND", "conditions": [{"path": [], "field": "version", "type": "int=", "value": 1}]}, 1, "运算符与字段类型不匹配"),
        ({"logic": "AND", "conditions": [{} for _ in range(11)]}, None, "筛选条件不能超过 10 个"),
    ],
)
def test_invalid_filter_points_at_the_condition(payload, index, message):
    with pytest.raises(AdvancedFilterError) as raised:
        _resolve(payload)
    assert raised.value.index == index
    assert message in str(raised.value)


def test_invisible_related_model_is_rejected():
    with pytest.raises(AdvancedFilterError) as raised:
        resolve_advanced_filter(
            "mysql",
            {
                "logic": "AND",
                "conditions": [{"path": ["mysql_run_host"], "field": "os_type", "type": "str=", "value": "linux"}],
            },
            ASSOCIATIONS,
            {"mysql"},
            ATTRS,
        )
    assert raised.value.index == 1
    assert "不可见" in str(raised.value)
