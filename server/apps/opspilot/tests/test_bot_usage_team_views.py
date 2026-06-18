"""Bot 使用组织(usage_team)功能回归测试:create 初始化 + authorize_usage_team 授权。

锁定不变式 team ⊆ usage_team:
- 新建 bot 时使用组织初始化为管理组织;
- 授权时管理组织恒并入、不可删除;
- 授权空列表 = 撤销全部使用组织,仅留管理组织。

用 superuser + current_team cookie:superuser 通过 @HasPermission 与 get_has_permission /
_validate_org_field_permission(均对 superuser 放行),从而聚焦验证 _merge_usage_team 不变式逻辑。
"""

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.opspilot.models import Bot
from apps.opspilot.viewsets.bot_view import BotViewSet

pytestmark = pytest.mark.django_db


def _make_superuser():
    from apps.base.models import User

    user = User.objects.create_user(
        username="bot_usage_su",
        password="x",
        domain="domain.com",
        locale="en",
        group_list=[{"id": 1, "name": "T1"}],
        roles=["admin"],
    )
    user.is_superuser = True
    user.save()
    return user


def _post(action, user, current_team, body, pk=None):
    factory = APIRequestFactory()
    request = factory.post("/", data=body, format="json")
    force_authenticate(request, user=user)
    request.COOKIES["current_team"] = str(current_team)
    view = BotViewSet.as_view({"post": action})
    return view(request, pk=pk) if pk is not None else view(request)


class TestBotUsageTeam:
    def test_create_initializes_usage_team_to_management_team(self):
        resp = _post("create", _make_superuser(), 1, {"name": "ub", "team": [1]})
        assert resp.status_code == 200
        bot = Bot.objects.get(name="ub")
        assert bot.team == [1]
        assert bot.usage_team == [1]  # 使用组织初始 = 管理组织

    def test_authorize_adds_usage_orgs_keeping_management(self):
        bot = Bot.objects.create(name="ab", team=[1], usage_team=[1])
        resp = _post("authorize_usage_team", _make_superuser(), 1, {"usage_team": [1, 2, 3]}, pk=bot.id)
        assert resp.status_code == 200
        bot.refresh_from_db()
        assert bot.usage_team == [1, 2, 3]

    def test_authorize_forces_management_org_into_usage(self):
        """请求即便不含管理组织,也强制并入(管理组织不可从使用组织删除)。"""
        bot = Bot.objects.create(name="ab2", team=[1], usage_team=[1, 2])
        resp = _post("authorize_usage_team", _make_superuser(), 1, {"usage_team": [2]}, pk=bot.id)
        assert resp.status_code == 200
        bot.refresh_from_db()
        assert bot.usage_team == [1, 2]  # 管理组织 1 恒在

    def test_authorize_empty_keeps_management_only(self):
        bot = Bot.objects.create(name="ab3", team=[1], usage_team=[1, 2])
        resp = _post("authorize_usage_team", _make_superuser(), 1, {"usage_team": []}, pk=bot.id)
        assert resp.status_code == 200
        bot.refresh_from_db()
        assert bot.usage_team == [1]  # 撤销全部使用组织,仅留管理组织
