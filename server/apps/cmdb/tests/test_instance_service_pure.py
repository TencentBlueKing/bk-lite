"""CMDB InstanceManage 纯逻辑方法覆盖测试（不触图数据库）。

对照 spec/prd/CMDB·视图/资产：拓扑节点权限裁剪、校验属性映射、权限过滤参数、导入结果消息。
"""

from types import SimpleNamespace

import pytest

from apps.cmdb.services.instance import InstanceManage as IM


# --------------------------------------------------------------------------
# _collect_topology_node_ids / _prune_topology_node
# --------------------------------------------------------------------------


def test_collect_topology_node_ids():
    node = {"_id": 1, "children": [{"_id": 2, "children": [{"_id": 3}]}, {"_id": 4}]}
    assert IM._collect_topology_node_ids(node) == {1, 2, 3, 4}


def test_collect_topology_node_ids_non_dict():
    assert IM._collect_topology_node_ids(None) == set()


def test_prune_topology_node_keeps_visible():
    node = {"_id": 1, "children": [{"_id": 2, "children": []}, {"_id": 3, "children": []}]}
    pruned = IM._prune_topology_node(node, visible_ids={2}, center_id=1)
    child_ids = {c["_id"] for c in pruned["children"]}
    assert child_ids == {2}  # 3 不可见被裁剪


def test_prune_topology_node_drops_invisible_root():
    node = {"_id": 5, "children": []}
    assert IM._prune_topology_node(node, visible_ids=set(), center_id=1) == {}


def test_prune_topology_node_non_dict():
    assert IM._prune_topology_node(None, set(), 1) == {}


# --------------------------------------------------------------------------
# _has_topology_view_permission
# --------------------------------------------------------------------------


def test_has_topology_view_permission_none_instance():
    assert IM._has_topology_view_permission(None, {}) is False


def test_has_topology_view_permission_no_permission_map():
    assert IM._has_topology_view_permission({"_id": 1}, None) is True


def test_has_topology_view_permission_creator_org_match():
    instance = {"_creator": "alice", "organization": [4], "model_id": "host"}
    permission_map = {4: {"permission_instances_map": {}}}
    user = SimpleNamespace(username="alice")
    assert IM._has_topology_view_permission(instance, permission_map, user=user) is True


# --------------------------------------------------------------------------
# _filter_topology_result
# --------------------------------------------------------------------------


def test_filter_topology_result_no_permission_map():
    result = {"src_result": {"_id": 1}}
    assert IM._filter_topology_result(result, 1, permission_map=None) is result


def test_filter_topology_result_not_dict():
    assert IM._filter_topology_result("x", 1, permission_map={1: {}}) == "x"


# --------------------------------------------------------------------------
# _build_format_permission_dict
# --------------------------------------------------------------------------


def test_build_format_permission_dict_with_inst_names():
    pmap = {4: {"inst_names": ["vc1"]}}
    out = IM._build_format_permission_dict(pmap, creator="admin")
    assert any(q["field"] == "inst_name" for q in out[4])
    assert any(q["field"] == "_creator" for q in out[4])


def test_build_format_permission_dict_empty():
    pmap = {4: {"inst_names": []}}
    out = IM._build_format_permission_dict(pmap)
    assert out[4] == []


# --------------------------------------------------------------------------
# _build_check_attr_map
# --------------------------------------------------------------------------


def test_build_check_attr_map():
    attrs = [
        {"attr_id": "name", "attr_name": "名称", "is_only": True, "is_required": True},
        {"attr_id": "desc", "attr_name": "描述", "editable": True},
    ]
    m = IM._build_check_attr_map(attrs, for_update=True)
    assert m["is_only"] == {"name": "名称"}
    assert m["is_required"] == {"name": "名称"}
    assert "desc" in m["editable"]


def test_build_check_attr_map_no_update():
    m = IM._build_check_attr_map([{"attr_id": "a", "attr_name": "A", "is_only": True}])
    assert "editable" not in m


# --------------------------------------------------------------------------
# format_result_message
# --------------------------------------------------------------------------


def test_format_result_message_all_success():
    result = {
        "add": {"success": 2, "error": 0, "data": []},
        "update": {"success": 1, "error": 0, "data": []},
        "asso": {"success": 0, "error": 0, "data": []},
    }
    status, msg = IM.format_result_message(result)
    assert status is True
    assert msg == ""


def test_format_result_message_with_failures():
    result = {
        "add": {"success": 1, "error": 1, "data": ["行2失败"]},
        "update": {"success": 0, "error": 0, "data": []},
        "asso": {"success": 0, "error": 0, "data": []},
    }
    status, msg = IM.format_result_message(result)
    assert status is False
    assert "失败" in msg


# --------------------------------------------------------------------------
# format_instance_permission_data / add_inst_name_permission
# --------------------------------------------------------------------------


def test_format_instance_permission_data_empty():
    assert IM.format_instance_permission_data(None) == []


def test_format_instance_permission_data_specific():
    rules = {1: {"host": [{"id": "vc1"}, {"id": "0"}]}}
    out = IM.format_instance_permission_data(rules)
    assert out == [{"model_id": "host", "inst_names": ["vc1"]}]


def test_format_instance_permission_data_all_select():
    rules = {1: {"host": [{"id": "0"}, {"id": "-1"}]}}
    assert IM.format_instance_permission_data(rules) == []


def test_add_inst_name_permission():
    assert IM.add_inst_name_permission([]) == ""
    assert IM.add_inst_name_permission(["a", "b"]) == "n.inst_name IN ['a', 'b']"
