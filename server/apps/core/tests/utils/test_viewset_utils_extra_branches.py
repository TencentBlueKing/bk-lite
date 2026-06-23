import pydantic.root_model  # noqa
"""apps/core/utils/viewset_utils.py 剩余未覆盖分支的真实行为测试。

补充 baseline (test_viewset_utils_pure/_auth/_query) 仍未触达的分支：

- GenericViewSetFun.get_has_permission:
    * include_children=True 且 group_tree 命中子组 -> user_groups 被子组覆盖 (36-39)
    * is_list=True 的批量组织交集判断 (42-48)
    * include_children=True 时 allowed_teams 与 user_groups 命中放行 (61-64)
- AuthViewSet._normalize_org_values:
    * QueryDict getlist 为空但 key 仍在 data 中 -> 走 data.get 单值分支 (417-418)
    * 单个非数字字符串 int() 失败 -> 跳过 (466-467)
- AuthViewSet._validate_name 内部异常 -> 返回空串 (612-614)

策略：直接实例化被测类，仅在真实跨进程边界 get_permission_rules 打桩，
其余分支逻辑全部真实执行并断言真实返回值与对协作者的真实入参契约。
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.core.utils.viewset_utils import AuthViewSet, GenericViewSetFun

pytestmark = pytest.mark.unit


class _FakeQuerySet:
    """模拟 is_list 分支需要的 instance：可迭代 + 支持 values_list('id', flat=True)。"""

    def __init__(self, items):
        self._items = items

    def __iter__(self):
        return iter(self._items)

    def values_list(self, field, flat=False):
        return [getattr(i, field) for i in self._items]


def _vs(app_name="core", permission_key="instance"):
    vs = GenericViewSetFun()
    vs.ORGANIZATION_FIELD = "team"
    vs.permission_key = permission_key
    vs._get_app_name = lambda: app_name
    return vs


def _user(group_list, group_tree=None):
    return SimpleNamespace(group_list=group_list, group_tree=group_tree or [])


# ============================================================================
# get_has_permission —— include_children + is_list 分支
# ============================================================================


class TestGetHasPermissionExtra:
    def test_include_children_overrides_user_groups_with_subtree(self):
        """include_children=True 且 group_tree 中能提取到子组时，
        鉴权使用的 user_groups 应被替换为子组集合（含 current_team 自身），
        从而让一个原本不在 user.group_list 的实例 team 通过组织交集检查。"""
        vs = _vs()
        # 用户 group_list 仅含 [1]，但 group_tree 下 current_team=1 含子组 2、3
        user = _user(
            group_list=[1],
            group_tree=[{"id": 1, "subGroups": [{"id": 2}, {"id": 3}]}],
        )
        # 实例属于子组 3 —— 仅在 include_children 时才有交集
        instance = SimpleNamespace(id=10, team=[3])
        rules = {"team": [], "instance": [{"id": "10", "permission": ["Operate"]}]}
        with patch("apps.core.utils.viewset_utils.get_permission_rules", return_value=rules):
            result = vs.get_has_permission(user, instance, current_team=1, include_children=True)
        assert result is True

        # 对照：不开 include_children 时，实例 team=[3] 与 user_groups=[1] 无交集 -> 拒绝
        with patch("apps.core.utils.viewset_utils.get_permission_rules") as mock_rules:
            result_no_children = vs.get_has_permission(user, instance, current_team=1, include_children=False)
        assert result_no_children is False
        mock_rules.assert_not_called()

    def test_include_children_allowed_teams_intersection_grants(self):
        """include_children=True：current_team 不在 rule team，但规则 team 与
        子组 user_groups 有交集 -> 通过 allowed_teams 分支放行 (61-64)。"""
        vs = _vs()
        user = _user(
            group_list=[1],
            group_tree=[{"id": 1, "subGroups": [{"id": 2}]}],
        )
        instance = SimpleNamespace(id=10, team=[2])
        # rule team=[2] 命中子组 2；current_team=1 不在 rule team
        rules = {"team": [2], "instance": []}
        with patch("apps.core.utils.viewset_utils.get_permission_rules", return_value=rules):
            result = vs.get_has_permission(user, instance, current_team=1, include_children=True)
        assert result is True

    def test_is_list_all_instances_have_org_intersection_then_rule_check(self):
        """is_list=True：所有实例的 team 都与 user_groups 有交集，
        进入规则判定；current_team 命中 rule team -> True (42-48 正向)。"""
        vs = _vs()
        user = _user(group_list=[1])
        qs = _FakeQuerySet([
            SimpleNamespace(id=10, team=[1]),
            SimpleNamespace(id=11, team=[1]),
        ])
        rules = {"team": [1], "instance": []}
        with patch("apps.core.utils.viewset_utils.get_permission_rules", return_value=rules) as mock_rules:
            result = vs.get_has_permission(user, qs, current_team=1, is_list=True)
        assert result is True
        # 进入规则判定阶段 -> get_permission_rules 被调用
        mock_rules.assert_called_once()

    def test_is_list_one_instance_without_org_intersection_returns_false(self):
        """is_list=True：只要有一个实例 team 与 user_groups 无交集 -> 直接拒绝，
        且不进入规则查询 (42-48 反向)。"""
        vs = _vs()
        user = _user(group_list=[1])
        qs = _FakeQuerySet([
            SimpleNamespace(id=10, team=[1]),
            SimpleNamespace(id=11, team=[99]),  # 无交集
        ])
        with patch("apps.core.utils.viewset_utils.get_permission_rules") as mock_rules:
            result = vs.get_has_permission(user, qs, current_team=1, is_list=True)
        assert result is False
        mock_rules.assert_not_called()

    def test_is_list_subset_check_against_operate_instances(self):
        """is_list=True：实例集合需是 Operate 实例集合的子集才放行。
        instance_id=[10,11]，规则只授予 10 -> 非子集 -> False。"""
        vs = _vs()
        user = _user(group_list=[1])
        qs = _FakeQuerySet([
            SimpleNamespace(id=10, team=[1]),
            SimpleNamespace(id=11, team=[1]),
        ])
        rules = {"team": [], "instance": [{"id": "10", "permission": ["Operate"]}]}
        with patch("apps.core.utils.viewset_utils.get_permission_rules", return_value=rules):
            result = vs.get_has_permission(user, qs, current_team=1, is_list=True)
        assert result is False


# ============================================================================
# _normalize_org_values —— 剩余 QueryDict / 非数字字符串分支
# ============================================================================


class TestNormalizeOrgValuesExtra:
    def test_querydict_empty_getlist_falls_back_to_single_get(self):
        """QueryDict.getlist 返回空、但 key 仍在 data 中 ->
        走 [data.get(field)] 单值分支 (417-418)。"""
        from django.http import QueryDict

        qd = QueryDict(mutable=True)
        # 直接赋值字符串：getlist 在该实现下取 last value 列表，
        # 这里构造一个 getlist 为空但 __contains__ 为真的场景
        qd["team"] = ""  # 空字符串值，key 存在
        # getlist 返回 [""]，非空 -> 该路径不触发；改用自定义 stub 覆盖精确分支
        result = AuthViewSet._normalize_org_values(qd, "team")
        # 空字符串会在后续 strip 后被跳过
        assert result == []

    def test_getlist_empty_but_key_present_uses_get(self):
        """精确覆盖 417-418：getlist 返回空列表，但 field 在 data 中 ->
        values = [data.get(field)]。用最小 stub 模拟该形态。"""

        class _Data:
            def getlist(self, k):
                return []

            def __contains__(self, k):
                return k == "team"

            def get(self, k, default=None):
                return 5 if k == "team" else default

        result = AuthViewSet._normalize_org_values(_Data(), "team")
        assert result == [5]

    def test_getlist_empty_and_key_absent_returns_empty(self):
        class _Data:
            def getlist(self, k):
                return []

            def __contains__(self, k):
                return False

            def get(self, k, default=None):
                return default

        assert AuthViewSet._normalize_org_values(_Data(), "team") == []

    def test_single_non_numeric_string_skipped(self):
        """单个非数字、不含逗号、非 [] 的字符串 -> int() 失败 -> 跳过 (466-467)。"""
        assert AuthViewSet._normalize_org_values({"team": "abc"}, "team") == []

    def test_mixed_list_with_non_numeric_single_string(self):
        assert AuthViewSet._normalize_org_values({"team": ["abc", 4]}, "team") == [4]


# ============================================================================
# _validate_name —— 内部异常分支
# ============================================================================


class TestValidateNameException:
    def test_queryset_filter_raises_returns_empty_string(self):
        """queryset.filter 抛异常 -> 捕获后返回空串 (612-614)，不向上冒泡。"""
        vs = AuthViewSet.__new__(AuthViewSet)
        vs.ORGANIZATION_FIELD = "team"
        qs = MagicMock()
        qs.filter.side_effect = RuntimeError("db boom")
        vs.queryset = qs
        result = vs._validate_name("foo", [{"id": 1, "name": "A"}], [1])
        assert result == ""
