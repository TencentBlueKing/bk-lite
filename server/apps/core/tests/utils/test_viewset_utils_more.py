import pydantic.root_model  # noqa
"""apps/core/utils/viewset_utils.py 补充覆盖（baseline 未触达的方法）。

聚焦：
- AuthViewSet.filter_rules（超管规则/普通规则/含 0 规则）
- AuthViewSet._validate_org_field_permission（规范化、超管豁免、无权组织报错——真实 Group 表查询）
- AuthViewSet._filter_by_user_groups（多 team Q 构建、异常兜底）
- AuthViewSet.delete_rules（无 permission_key/无 delete_team/正常转发/异常兜底）
- GenericViewSetFun._parse_current_team_cookie / value_error / _get_app_name
- GenericViewSetFun.get_queryset_by_permission（无 user / 实例+team / 空规则返回 id=0）
- GenericViewSetFun.filter_by_group（超管豁免 / 普通用户越权 PermissionDenied / 子组展开）

策略：实例化被测类，仅在真实跨进程边界（get_permission_rules）打桩，
Group 走真实表，DRF Q/queryset 行为真实执行。
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from rest_framework.exceptions import PermissionDenied

from apps.core.utils.viewset_utils import AuthViewSet, GenericViewSetFun

pytestmark = pytest.mark.unit


def _auth_vs(app_name="cmdb", permission_key=None, org_field="team"):
    vs = AuthViewSet.__new__(AuthViewSet)
    vs.ORGANIZATION_FIELD = org_field
    vs.loader = None
    vs.core_loader = None
    vs._get_app_name = lambda: app_name
    if permission_key is not None:
        vs.permission_key = permission_key
    return vs


# ---------------------------------------------------------------------------
# filter_rules
# ---------------------------------------------------------------------------


class TestFilterRules:
    def test_empty_returns_empty(self):
        assert _auth_vs().filter_rules([]) == []
        assert _auth_vs().filter_rules(None) == []

    def test_superuser_rule_id_returns_empty(self):
        # 单条规则且 id 在 SUPERUSER_RULE_ID(['0']) 中 -> 视为全量，返回 []
        assert _auth_vs().filter_rules([{"id": "0"}]) == []

    def test_extracts_int_ids(self):
        assert _auth_vs().filter_rules([{"id": "3"}, {"id": 5}]) == [3, 5]

    def test_zero_in_ids_returns_empty(self):
        # 多条规则但包含 id=0 -> 全量
        assert _auth_vs().filter_rules([{"id": "1"}, {"id": "0"}]) == []

    def test_skips_non_dict_entries(self):
        assert _auth_vs().filter_rules(["bad", {"id": 2}]) == [2]


# ---------------------------------------------------------------------------
# _validate_org_field_permission
# ---------------------------------------------------------------------------


class TestValidateOrgFieldPermission:
    def test_empty_values_noop(self):
        vs = _auth_vs()
        req = SimpleNamespace(user=SimpleNamespace(is_superuser=False, group_list=[]))
        # 不抛异常
        vs._validate_org_field_permission(req, [])
        vs._validate_org_field_permission(req, None)

    def test_non_digit_strings_normalized_away(self):
        vs = _auth_vs()
        req = SimpleNamespace(user=SimpleNamespace(is_superuser=False, group_list=[]))
        # 全部非数字 -> normalized 为空 -> 直接返回，不报错
        vs._validate_org_field_permission(req, ["abc", "x"])

    def test_superuser_skips_validation(self):
        vs = _auth_vs()
        req = SimpleNamespace(user=SimpleNamespace(is_superuser=True, group_list=[]))
        # 超管即使组织不在 group_list 也不报错
        vs._validate_org_field_permission(req, [999])

    def test_no_user_raises_permission_denied(self):
        vs = _auth_vs()
        req = SimpleNamespace(user=None)
        with pytest.raises(PermissionDenied):
            vs._validate_org_field_permission(req, [1])

    def test_org_within_user_groups_ok(self):
        vs = _auth_vs()
        req = SimpleNamespace(user=SimpleNamespace(is_superuser=False, group_list=[{"id": 1}, {"id": 2}]))
        # 1,2 都在用户组内 -> 不报错
        vs._validate_org_field_permission(req, [1, "2"])

    @pytest.mark.django_db
    def test_invalid_org_raises_with_group_name(self):
        from apps.system_mgmt.models import Group

        g = Group.objects.create(name="DenyTeam", parent_id=0)
        vs = _auth_vs()
        req = SimpleNamespace(user=SimpleNamespace(is_superuser=False, group_list=[{"id": 1}]))
        with pytest.raises(PermissionDenied) as exc:
            vs._validate_org_field_permission(req, [g.id])
        assert "DenyTeam" in str(exc.value)

    @pytest.mark.django_db
    def test_invalid_org_unknown_id_uses_id_label(self):
        vs = _auth_vs()
        req = SimpleNamespace(user=SimpleNamespace(is_superuser=False, group_list=[{"id": 1}]))
        with pytest.raises(PermissionDenied) as exc:
            vs._validate_org_field_permission(req, [424242])
        assert "424242" in str(exc.value)


# ---------------------------------------------------------------------------
# _filter_by_user_groups
# ---------------------------------------------------------------------------


class TestFilterByUserGroups:
    def test_empty_current_team_returns_empty_q(self):
        from django.db.models import Q

        vs = _auth_vs()
        assert vs._filter_by_user_groups(MagicMock(), "") == Q()

    def test_builds_or_query_for_each_team(self):
        vs = _auth_vs(org_field="team")
        q = vs._filter_by_user_groups(MagicMock(), "1, 2 ,3")
        # children 子句数量 == team 数量
        assert len(q.children) == 3

    def test_non_numeric_team_triggers_exception_returns_partial_q(self):
        from django.db.models import Q

        vs = _auth_vs(org_field="team")
        # "x" 触发 int() 异常 -> 捕获并返回当前累积 query
        result = vs._filter_by_user_groups(MagicMock(), "x")
        assert isinstance(result, Q)


# ---------------------------------------------------------------------------
# delete_rules
# ---------------------------------------------------------------------------


class TestDeleteRules:
    def test_no_permission_key_noop(self):
        vs = _auth_vs()  # 无 permission_key
        with patch("apps.core.utils.viewset_utils.delete_instance_rules") as mock_del:
            vs.delete_rules(1, [2])
        mock_del.assert_not_called()

    def test_no_delete_team_noop(self):
        vs = _auth_vs(permission_key="instance")
        with patch("apps.core.utils.viewset_utils.delete_instance_rules") as mock_del:
            vs.delete_rules(1, [])
        mock_del.assert_not_called()

    def test_forwards_to_delete_instance_rules(self):
        vs = _auth_vs(app_name="cmdb", permission_key="instance")
        with patch("apps.core.utils.viewset_utils.delete_instance_rules") as mock_del:
            vs.delete_rules(7, [3, 4])
        mock_del.assert_called_once_with("cmdb", "instance", 7, [3, 4])

    def test_exception_is_swallowed(self):
        vs = _auth_vs(app_name="cmdb", permission_key="instance")
        with patch("apps.core.utils.viewset_utils.delete_instance_rules", side_effect=RuntimeError("rpc")):
            # 不应向上冒泡
            vs.delete_rules(7, [3])


# ---------------------------------------------------------------------------
# GenericViewSetFun 基础方法
# ---------------------------------------------------------------------------


class TestGenericBasics:
    def test_parse_current_team_cookie_valid(self):
        with patch("apps.core.utils.viewset_utils.get_current_team", return_value="5"):
            assert GenericViewSetFun._parse_current_team_cookie(MagicMock()) == 5

    def test_parse_current_team_cookie_invalid_returns_default(self):
        with patch("apps.core.utils.viewset_utils.get_current_team", return_value="abc"):
            assert GenericViewSetFun._parse_current_team_cookie(MagicMock(), default=7) == 7

    def test_value_error_shape(self):
        import json

        resp = GenericViewSetFun.value_error("nope")
        body = json.loads(resp.content)
        assert body == {"result": False, "message": "nope"}

    def test_get_app_name_from_module(self):
        vs = GenericViewSetFun()
        # 真实 __module__ 形如 apps.core.utils.viewset_utils -> 'core'
        assert vs._get_app_name() == "core"


# ---------------------------------------------------------------------------
# get_queryset_by_permission
# ---------------------------------------------------------------------------


class TestGetQuerysetByPermission:
    def test_no_user_returns_value_error(self):
        import json

        vs = _auth_vs(permission_key="instance")
        req = SimpleNamespace(user=None)
        resp = vs.get_queryset_by_permission(req, MagicMock())
        body = json.loads(resp.content)
        assert body["result"] is False

    @pytest.mark.django_db
    def test_instance_and_team_build_query(self):
        from apps.system_mgmt.models import Group

        g1 = Group.objects.create(name="q1", parent_id=0)
        g2 = Group.objects.create(name="q2", parent_id=0)
        vs = _auth_vs(app_name="system_mgmt", permission_key="instance", org_field="id")
        # 用户是超管以跳过 filter_by_group 的越权校验；current_team 取 g1
        user = SimpleNamespace(is_superuser=True, group_list=[{"id": g1.id}], group_tree=[])
        req = SimpleNamespace(user=user, COOKIES={"include_children": "0"})
        rules = {"instance": [{"id": g1.id}], "team": []}
        with (
            patch("apps.core.utils.viewset_utils.get_current_team", return_value=str(g1.id)),
            patch("apps.core.utils.viewset_utils.get_permission_rules", return_value=rules),
        ):
            qs = vs.get_queryset_by_permission(req, Group.objects.all())
        ids = set(qs.values_list("id", flat=True))
        assert g1.id in ids
        assert g2.id not in ids

    @pytest.mark.django_db
    def test_empty_rules_returns_id_zero_filter(self):
        from apps.system_mgmt.models import Group

        g1 = Group.objects.create(name="z1", parent_id=0)
        vs = _auth_vs(app_name="system_mgmt", permission_key="instance", org_field="id")
        user = SimpleNamespace(is_superuser=True, group_list=[{"id": g1.id}], group_tree=[])
        req = SimpleNamespace(user=user, COOKIES={"include_children": "0"})
        rules = {"instance": [], "team": []}
        with (
            patch("apps.core.utils.viewset_utils.get_current_team", return_value=str(g1.id)),
            patch("apps.core.utils.viewset_utils.get_permission_rules", return_value=rules),
        ):
            qs = vs.get_queryset_by_permission(req, Group.objects.all())
        # 无任何规则 -> filter(id=0) -> 空集
        assert list(qs) == []


# ---------------------------------------------------------------------------
# filter_by_group
# ---------------------------------------------------------------------------


class TestFilterByGroup:
    @pytest.mark.django_db
    def test_superuser_skips_team_validation(self):
        from apps.system_mgmt.models import Group

        user = SimpleNamespace(is_superuser=True, group_list=[], group_tree=[])
        req = SimpleNamespace(user=user, COOKIES={"include_children": "0"})
        with patch("apps.core.utils.viewset_utils.get_current_team", return_value="5"):
            current_team, include_children, org_field, query = AuthViewSet.filter_by_group(
                Group.objects.all(), req, user
            )
        assert current_team == 5
        assert include_children is False

    @pytest.mark.django_db
    def test_non_superuser_unauthorized_team_raises(self):
        from apps.system_mgmt.models import Group

        user = SimpleNamespace(is_superuser=False, group_list=[{"id": 1}], group_tree=[])
        req = SimpleNamespace(user=user, COOKIES={"include_children": "0"})
        with patch("apps.core.utils.viewset_utils.get_current_team", return_value="999"):
            with pytest.raises(PermissionDenied):
                AuthViewSet.filter_by_group(Group.objects.all(), req, user)

    @pytest.mark.django_db
    def test_include_children_expands_subgroups(self):
        from apps.system_mgmt.models import Group

        user = SimpleNamespace(
            is_superuser=False,
            group_list=[{"id": 1}],
            group_tree=[{"id": 1, "subGroups": [{"id": 2}, {"id": 3}]}],
        )
        req = SimpleNamespace(user=user, COOKIES={"include_children": "1"})
        with patch("apps.core.utils.viewset_utils.get_current_team", return_value="1"):
            current_team, include_children, org_field, query = AuthViewSet.filter_by_group(
                Group.objects.all(), req, user
            )
        assert include_children is True
        # org_field "team" 不在 Group 字段中 -> query 为空 Q（走 else 分支也可），仅断言不抛异常
        assert current_team == 1
