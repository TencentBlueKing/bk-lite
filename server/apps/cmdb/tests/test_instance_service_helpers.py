"""CMDB InstanceManage 纯逻辑/拓扑过滤/计数覆盖测试。

对照 spec/prd/CMDB·资产：组织范围校验、tag/enum 字段校验、权限过滤字典、校验属性映射、
拓扑节点裁剪与权限可见性、结果信息格式化、实例权限过滤参数、分组计数。
"""

import pytest

from apps.cmdb.services import instance as inst_mod
from apps.cmdb.services.instance import (
    InstanceManage,
    _normalize_allowed_org_ids,
    apply_enum_validation_for_instance,
    apply_tag_validation_for_batch,
    apply_tag_validation_for_instance,
    validate_instance_organization_scope,
)
from apps.core.exceptions.base_app_exception import BaseAppException

MODULE = "apps.cmdb.services.instance"


# --------------------------------------------------------------------------
# _normalize_allowed_org_ids
# --------------------------------------------------------------------------


def test_normalize_allowed_explicit():
    assert _normalize_allowed_org_ids(allowed_org_ids=[1, "2", None]) == {1, 2}


def test_normalize_allowed_user_groups_dict_and_int():
    assert _normalize_allowed_org_ids(user_groups=[{"id": 1}, 2, {"id": None}]) == {1, 2}


def test_normalize_allowed_bad_value():
    with pytest.raises(BaseAppException):
        _normalize_allowed_org_ids(allowed_org_ids=["x"])


# --------------------------------------------------------------------------
# validate_instance_organization_scope
# --------------------------------------------------------------------------


def test_validate_scope_no_org_key():
    validate_instance_organization_scope({"inst_name": "h"}, allowed_org_ids=[1])  # no raise


def test_validate_scope_empty_org():
    validate_instance_organization_scope({"organization": None}, allowed_org_ids=[1])


def test_validate_scope_not_list():
    with pytest.raises(BaseAppException):
        validate_instance_organization_scope({"organization": "x"}, allowed_org_ids=[1])


def test_validate_scope_in_range():
    validate_instance_organization_scope({"organization": [1]}, allowed_org_ids=[1, 2])


def test_validate_scope_out_of_range():
    with pytest.raises(BaseAppException):
        validate_instance_organization_scope({"organization": [9]}, allowed_org_ids=[1])


def test_validate_scope_missing_context():
    with pytest.raises(BaseAppException):
        validate_instance_organization_scope({"organization": [1]}, allowed_org_ids=[])


# --------------------------------------------------------------------------
# apply_tag_validation_for_instance / batch
# --------------------------------------------------------------------------

# TAG_ATTR_ID == "tag"
_TAG_ATTRS = [{"attr_id": "tag", "attr_type": "tag", "attr_name": "标签", "option": {"mode": "free"}}]


def test_apply_tag_no_tag_attr_pops():
    out = apply_tag_validation_for_instance({"tag": ["a:1"], "x": 1}, attrs=[])
    assert "tag" not in out and out["x"] == 1


def test_apply_tag_not_in_data():
    out = apply_tag_validation_for_instance({"x": 1}, attrs=_TAG_ATTRS)
    assert out == {"x": 1}


def test_apply_tag_valid():
    out = apply_tag_validation_for_instance({"tag": ["env:prod"]}, attrs=_TAG_ATTRS)
    assert out["tag"] == ["env:prod"]


def test_apply_tag_invalid_raises():
    with pytest.raises(BaseAppException):
        apply_tag_validation_for_instance({"tag": ["noseparator"]}, attrs=_TAG_ATTRS)


def test_apply_tag_batch_no_attr():
    out = apply_tag_validation_for_batch([{"tag": ["a:1"], "x": 1}], attrs=[])
    assert out == [{"x": 1}]


def test_apply_tag_batch_valid():
    out = apply_tag_validation_for_batch([{"tag": ["env:prod"]}, {"x": 1}], attrs=_TAG_ATTRS)
    assert out[0]["tag"] == ["env:prod"]


# --------------------------------------------------------------------------
# apply_enum_validation_for_instance
# --------------------------------------------------------------------------

_ENUM_ATTRS = [
    {
        "attr_id": "status", "attr_type": "enum", "enum_select_mode": "single",
        "is_required": False, "option": [{"id": "1", "name": "运行"}, {"id": "2", "name": "停止"}],
    }
]


def test_apply_enum_valid():
    out = apply_enum_validation_for_instance({"status": "1"}, attrs=_ENUM_ATTRS)
    assert out["status"] == ["1"]


def test_apply_enum_invalid_option():
    with pytest.raises(BaseAppException):
        apply_enum_validation_for_instance({"status": "9"}, attrs=_ENUM_ATTRS)


def test_apply_enum_attr_not_in_data():
    out = apply_enum_validation_for_instance({"x": 1}, attrs=_ENUM_ATTRS)
    assert out == {"x": 1}


# --------------------------------------------------------------------------
# _build_format_permission_dict / _build_check_attr_map
# --------------------------------------------------------------------------


def test_build_format_permission_dict():
    pmap = {1: {"inst_names": ["h1"]}, 2: {"inst_names": []}}
    out = InstanceManage._build_format_permission_dict(pmap, creator="alice")
    assert out[1][0]["field"] == "inst_name"
    assert any(q["field"] == "_creator" for q in out[1])
    assert out[2] == []


def test_build_check_attr_map():
    attrs = [
        {"attr_id": "name", "attr_name": "名称", "is_only": True, "is_required": True},
        {"attr_id": "desc", "attr_name": "描述", "editable": True},
    ]
    out = InstanceManage._build_check_attr_map(attrs, for_update=True)
    assert out["is_only"] == {"name": "名称"}
    assert out["is_required"] == {"name": "名称"}
    assert out["editable"] == {"desc": "描述"}


# --------------------------------------------------------------------------
# topology helpers
# --------------------------------------------------------------------------


def test_collect_topology_node_ids():
    node = {"_id": 1, "children": [{"_id": 2, "children": [{"_id": 3}]}, {"_id": "bad"}]}
    assert InstanceManage._collect_topology_node_ids(node) == {1, 2, 3}


def test_prune_topology_node():
    node = {"_id": 1, "children": [{"_id": 2}, {"_id": 3}]}
    pruned = InstanceManage._prune_topology_node(node, visible_ids={2}, center_id=1)
    child_ids = {c["_id"] for c in pruned["children"]}
    assert child_ids == {2}  # 3 不可见被裁剪


def test_filter_topology_result_no_permission_map():
    result = {"src_result": {"_id": 1}, "dst_result": {"_id": 1}}
    assert InstanceManage._filter_topology_result(result, 1, permission_map=None) is result


def test_has_topology_view_permission_none_instance():
    assert InstanceManage._has_topology_view_permission(None, {1: {}}) is False


def test_has_topology_view_permission_no_map():
    assert InstanceManage._has_topology_view_permission({"_id": 1}, None) is True


def test_has_topology_view_permission_creator(monkeypatch):
    from types import SimpleNamespace

    user = SimpleNamespace(username="alice")
    instance = {"_id": 1, "_creator": "alice", "organization": [1], "model_id": "host"}
    assert InstanceManage._has_topology_view_permission(instance, {1: {}}, user=user) is True


# --------------------------------------------------------------------------
# format_result_message / format_instance_permission_data / add_inst_name_permission
# --------------------------------------------------------------------------


def test_format_result_message_all_success():
    result = {
        "add": {"success": 2, "error": 0, "data": []},
        "update": {"success": 1, "error": 0, "data": []},
        "asso": {"success": 0, "error": 0, "data": []},
    }
    status, msg = InstanceManage.format_result_message(result)
    assert status is True and msg == ""


def test_format_result_message_with_failure():
    result = {
        "add": {"success": 1, "error": 1, "data": ["行2失败"]},
        "update": {"success": 0, "error": 0, "data": []},
        "asso": {"success": 0, "error": 0, "data": []},
    }
    status, msg = InstanceManage.format_result_message(result)
    assert status is False and "失败1个" in msg


def test_format_instance_permission_data():
    rules = {1: {"host": [{"id": "0"}, {"id": "VC3"}], "sw": [{"id": "-1"}]}}
    out = InstanceManage.format_instance_permission_data(rules)
    assert out == [{"model_id": "host", "inst_names": ["VC3"]}]


def test_format_instance_permission_data_empty():
    assert InstanceManage.format_instance_permission_data(None) == []


def test_add_inst_name_permission():
    assert InstanceManage.add_inst_name_permission([]) == ""
    assert "inst_name IN" in InstanceManage.add_inst_name_permission(["h1"])


# --------------------------------------------------------------------------
# graph-backed: search_inst / group_inst_count / topo_search
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_search_inst(fake_graph):
    fake_graph(MODULE, query_entity=([{"_id": 1, "inst_name": "h"}], 1))
    insts, count = InstanceManage.search_inst("host", inst_name="h", _id=1)
    assert count == 1


@pytest.mark.django_db
def test_search_inst_supports_bounded_page(fake_graph):
    fg = fake_graph(MODULE, query_entity=([{"_id": 2}], 3))

    InstanceManage.search_inst("host", page=2, page_size=1)

    call = next(item for item in fg.calls if item[0] == "query_entity")
    assert call[2]["page"] == {"skip": 1, "limit": 1}


@pytest.mark.django_db
def test_group_inst_count(fake_graph):
    fg = fake_graph(MODULE, entity_count=[{"model_id": "host", "count": 3}])
    out = InstanceManage.group_inst_count("model_id", permissions_map={1: {"inst_names": []}})
    assert out[0]["count"] == 3
    assert any(c[0] == "entity_count" for c in fg.calls)


@pytest.mark.django_db
def test_topo_search(fake_graph):
    fake_graph(MODULE, query_topo={"src_result": {"_id": 1}})
    out = InstanceManage.topo_search(1)
    assert out["src_result"]["_id"] == 1


@pytest.mark.django_db
def test_topo_search_lite_filters(fake_graph):
    fake_graph(MODULE, query_topo_lite={"src_result": {"_id": 1, "children": []}, "dst_result": {"_id": 1, "children": []}})
    # 无 permission_map → 原样返回
    out = InstanceManage.topo_search_lite(1, depth=2)
    assert out["src_result"]["_id"] == 1
