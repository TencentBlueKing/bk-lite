"""视图 mixin / 基类的单测（C3 补完）

- TeamResolveMixin.resolve_user_team：API-Secret / cookie / 回退 / 异常分支
- BaseDangerousItemViewSet.get_serializer_class：按 action 选择序列化器
"""

from types import SimpleNamespace

import pytest

from apps.job_mgmt.views.mixins import TeamResolveMixin


def _request(*, group_list, api_pass=False, current_team=None, is_superuser=False):
    cookies = {} if current_team is None else {"current_team": str(current_team)}
    user = SimpleNamespace(group_list=group_list, is_superuser=is_superuser)
    return SimpleNamespace(user=user, api_pass=api_pass, COOKIES=cookies)


@pytest.mark.unit
class TestTeamResolveMixin:
    def setup_method(self):
        self.mixin = TeamResolveMixin()

    def test_no_groups_returns_error(self):
        team, err = self.mixin.resolve_user_team(_request(group_list=[]))
        assert team is None
        assert err == "用户未关联团队"

    def test_api_secret_uses_first_group(self):
        team, err = self.mixin.resolve_user_team(_request(group_list=[{"id": 7}, {"id": 8}], api_pass=True))
        assert team == 7
        assert err is None

    def test_api_secret_supports_plain_int_group_list(self):
        team, err = self.mixin.resolve_user_team(_request(group_list=[5], api_pass=True))
        assert team == 5
        assert err is None

    def test_cookie_team_used_when_authorized(self):
        team, err = self.mixin.resolve_user_team(_request(group_list=[{"id": 3}], current_team=3))
        assert team == 3
        assert err is None

    def test_cookie_team_rejected_when_not_authorized(self):
        team, err = self.mixin.resolve_user_team(_request(group_list=[{"id": 3}], current_team=99))
        assert team is None
        assert err == "无权访问该团队数据"

    def test_superuser_cookie_team_not_restricted(self):
        team, err = self.mixin.resolve_user_team(_request(group_list=[{"id": 3}], current_team=99, is_superuser=True))
        assert team == 99
        assert err is None

    def test_invalid_cookie_returns_error(self):
        team, err = self.mixin.resolve_user_team(_request(group_list=[{"id": 3}], current_team="abc"))
        assert team is None
        assert err == "current_team 参数非法"

    def test_no_cookie_falls_back_to_first_group(self):
        team, err = self.mixin.resolve_user_team(_request(group_list=[{"id": 4}, {"id": 5}]))
        assert team == 4
        assert err is None


@pytest.mark.unit
@pytest.mark.django_db
class TestBaseDangerousItemViewSetSerializer:
    """两个高危 ViewSet 继承基类后，get_serializer_class 按 action 正确路由。"""

    def _serializer_for(self, viewset_cls, action):
        vs = viewset_cls()
        vs.action = action
        return vs.get_serializer_class()

    def test_dangerous_rule_serializer_routing(self):
        from apps.job_mgmt.serializers.dangerous_rule import DangerousRuleCreateSerializer, DangerousRuleSerializer, DangerousRuleUpdateSerializer
        from apps.job_mgmt.views.dangerous_rule import DangerousRuleViewSet

        assert self._serializer_for(DangerousRuleViewSet, "create") is DangerousRuleCreateSerializer
        assert self._serializer_for(DangerousRuleViewSet, "update") is DangerousRuleUpdateSerializer
        assert self._serializer_for(DangerousRuleViewSet, "partial_update") is DangerousRuleUpdateSerializer
        assert self._serializer_for(DangerousRuleViewSet, "list") is DangerousRuleSerializer
        assert self._serializer_for(DangerousRuleViewSet, "retrieve") is DangerousRuleSerializer

    def test_dangerous_path_serializer_routing(self):
        from apps.job_mgmt.serializers.dangerous_path import DangerousPathCreateSerializer, DangerousPathSerializer, DangerousPathUpdateSerializer
        from apps.job_mgmt.views.dangerous_path import DangerousPathViewSet

        assert self._serializer_for(DangerousPathViewSet, "create") is DangerousPathCreateSerializer
        assert self._serializer_for(DangerousPathViewSet, "update") is DangerousPathUpdateSerializer
        assert self._serializer_for(DangerousPathViewSet, "list") is DangerousPathSerializer

    def test_subclasses_inherit_base(self):
        from apps.job_mgmt.views.dangerous_base import BaseDangerousItemViewSet
        from apps.job_mgmt.views.dangerous_path import DangerousPathViewSet
        from apps.job_mgmt.views.dangerous_rule import DangerousRuleViewSet

        assert issubclass(DangerousPathViewSet, BaseDangerousItemViewSet)
        assert issubclass(DangerousRuleViewSet, BaseDangerousItemViewSet)
        # 日志参数化字段
        assert DangerousPathViewSet.dangerous_name_field == "pattern"
        assert DangerousRuleViewSet.dangerous_name_field == "name"
