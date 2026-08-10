"""CMDB 权限规则格式化工具覆盖测试。

对照 specs/capabilities/legacy-prd-cmdb-资产.md：实例/模型按组织与实例级权限规则判定可见/可操作。
"""

from types import SimpleNamespace

import pytest

from apps.cmdb.constants.constants import OPERATE, VIEW
from apps.cmdb.utils.permission_util import CmdbRulesFormatUtil as U


# --------------------------------------------------------------------------
# normalize helpers
# --------------------------------------------------------------------------


def test_normalize_user_group_ids_mixed():
    assert U._normalize_user_group_ids([{"id": 1}, 2, {"id": None}, None]) == [1, 2]


def test_normalize_user_group_ids_empty():
    assert U._normalize_user_group_ids(None) == []


def test_normalize_team_rule_ids():
    assert U._normalize_team_rule_ids([{"id": 1}, 2, {"id": "x"}, None]) == {1, 2}


# --------------------------------------------------------------------------
# build_deny_permission_data
# --------------------------------------------------------------------------


def test_build_deny_permission_data():
    data = U.build_deny_permission_data()
    assert "permission_instances_map" in data
    assert len(data["inst_names"]) == 1


# --------------------------------------------------------------------------
# format_permission_instances_list / count_list
# --------------------------------------------------------------------------


def test_format_permission_instances_list():
    instances = [{"id": "vc1", "permission": ["View"]}, {"id": "-1", "permission": ["Operate"]}]
    result = U.format_permission_instances_list(instances)
    assert result == {"vc1": ["View"]}  # -1 跳过


def test_format_permission_instances_count_list():
    rules = {"host": {"instance": [{"id": "h1", "permission": ["View"]}, {"id": "-1", "permission": ["x"]}]}}
    result = U.format_permission_instances_count_list(rules)
    assert result == {"h1": ["View"]}


# --------------------------------------------------------------------------
# build_permission_rule_map
# --------------------------------------------------------------------------


def test_build_permission_rule_map_team_full_access():
    # team 在 team 规则中 → 全量访问（空 map）
    result = U.build_permission_rule_map(
        user_teams=[1], permission_rules={"team": [{"id": 1}], "instance": []}
    )
    assert result[1]["permission_instances_map"] == {}


def test_build_permission_rule_map_instance_scoped():
    result = U.build_permission_rule_map(
        user_teams=[2], permission_rules={"team": [], "instance": [{"id": "vc1", "permission": ["View"]}]}
    )
    assert "vc1" in result[2]["permission_instances_map"]


def test_build_permission_rule_map_deny():
    # 无 team 无 instance → deny
    result = U.build_permission_rule_map(
        user_teams=[3], permission_rules={"team": [], "instance": []}
    )
    assert result[3]["inst_names"]  # deny placeholder


def test_build_permission_rule_map_fallback():
    result = U.build_permission_rule_map(
        user_teams=[], permission_rules={"team": [], "instance": []}, fallback_team_id=9
    )
    assert 9 in result


# --------------------------------------------------------------------------
# format_search_query_list / pop / search organizations
# --------------------------------------------------------------------------


def test_format_search_query_list_adds_org():
    out = U.format_search_query_list(5, [{"field": "name", "type": "str=", "value": "x"}])
    assert any(q["field"] == "organization" for q in out)


def test_format_search_query_list_keeps_existing_org():
    ql = [{"field": "organization", "type": "list[]", "value": [1]}]
    out = U.format_search_query_list(5, ql)
    org_queries = [q for q in out if q["field"] == "organization"]
    assert len(org_queries) == 1


def test_pop_organization_query_list():
    ql = [{"field": "organization", "value": [1]}, {"field": "name", "value": "x"}]
    out = U.pop_organization_query_list(ql, {})
    assert all(q["field"] != "organization" for q in out)


def test_search_organizations():
    ql = [{"field": "organization", "value": [1, 2]}, {"field": "name", "value": "x"}]
    assert U.search_organizations(ql) == [1, 2]


# --------------------------------------------------------------------------
# format_organizations_instances_map
# --------------------------------------------------------------------------


def test_format_organizations_instances_map_no_conditions_full_access():
    pmap = {4: {"permission_instances_map": {}}}
    out = U.format_organizations_instances_map(pmap)
    assert out[4]["permission"] == {VIEW, OPERATE}


def test_format_organizations_instances_map_default_model():
    pmap = {4: {"permission_instances_map": {}, "__default_model": True}}
    out = U.format_organizations_instances_map(pmap)
    assert out[4]["permission"] == {VIEW}


def test_format_organizations_instances_map_instance_scoped():
    pmap = {6: {"permission_instances_map": {"VC3": ["View", "Operate"]}}}
    out = U.format_organizations_instances_map(pmap)
    assert out["VC3"]["permission"] == {"View", "Operate"}


# --------------------------------------------------------------------------
# has_object_permission
# --------------------------------------------------------------------------


def test_has_object_permission_instances_by_org():
    pmap = {6: {"permission_instances_map": {}}}  # org 6 全选
    instance = {"inst_name": "vc", "organization": [6]}
    assert U.has_object_permission("instances", VIEW, "vmware", pmap, instance) is True


def test_has_object_permission_instances_no_access():
    pmap = {6: {"permission_instances_map": {"other": ["View"]}}}
    instance = {"inst_name": "vc", "organization": [99]}
    assert U.has_object_permission("instances", VIEW, "vmware", pmap, instance) is False


def test_has_object_permission_instances_same_name_other_org_denied():
    pmap = {6: {"permission_instances_map": {"prod-vc": ["View"]}}}
    instance = {"inst_name": "prod-vc", "organization": [9]}
    assert U.has_object_permission("instances", VIEW, "vmware_vc", pmap, instance) is False


def test_has_object_permission_instances_same_name_same_org_allowed():
    pmap = {6: {"permission_instances_map": {"prod-vc": ["View"]}}}
    instance = {"inst_name": "prod-vc", "organization": [6]}
    assert U.has_object_permission("instances", VIEW, "vmware_vc", pmap, instance) is True


def test_has_object_permission_instances_same_name_ignores_other_org_permissions():
    pmap = {
        6: {"permission_instances_map": {"prod-vc": ["View"]}},
        8: {"permission_instances_map": {"prod-vc": ["Operate"]}},
    }
    instance = {"inst_name": "prod-vc", "organization": [6]}
    assert U.has_object_permission("instances", VIEW, "vmware_vc", pmap, instance) is True
    assert U.has_object_permission("instances", OPERATE, "vmware_vc", pmap, instance) is False


def test_has_object_permission_model_same_model_id_other_org_denied():
    pmap = {6: {"permission_instances_map": {"vmware_vc": ["Operate"]}}}
    model = {"model_id": "vmware_vc", "group": [9]}
    assert U.has_object_permission("model", OPERATE, "vmware_vc", pmap, model, default_group_id=1) is False


def test_has_object_permission_model_same_org_allowed():
    pmap = {6: {"permission_instances_map": {"vmware_vc": ["Operate"]}}}
    model = {"model_id": "vmware_vc", "group": [6]}
    assert U.has_object_permission("model", OPERATE, "vmware_vc", pmap, model, default_group_id=1) is True
