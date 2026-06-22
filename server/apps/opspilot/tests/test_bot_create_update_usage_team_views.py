"""Bot create/update 显式 usage_team 处理的回归测试(补 d01ae8edf 引入分支)。

d01ae8edf 让 create/update 支持显式传入 usage_team:
- create: usage_team 默认并入管理组织(不变式 team ⊆ usage_team);额外使用组织单独校验权限;
- update: 当请求体含 usage_team 时,校验"额外的非管理组织"权限并强制并入管理组织;
- update: 仅变更 team(不含 usage_team)时,沿用 elif 分支维持不变式。

既有 test_bot_usage_team_views.py 仅覆盖 create 默认初始化 + authorize_usage_team action,
本文件补齐 create 显式 usage_team 与 update 两条分支的覆盖。

harness 与既有用例一致:superuser + current_team cookie,经 @HasPermission /
get_has_permission / _validate_org_field_permission(均对 superuser 放行),
聚焦验证 _merge_usage_team 不变式与 update 分支逻辑。
"""

from unittest.mock import patch

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.models import User
from apps.opspilot.models import Bot
from apps.opspilot.viewsets.bot_view import BotViewSet

pytestmark = pytest.mark.django_db


def _make_superuser(username="bot_cu_su"):
    user = User.objects.create_user(
        username=username,
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


def _make_normal_user(username, group_ids, permission):
    """构造非超管用户:group_list 决定可管理组织,permission 决定 @HasPermission 放行。"""
    user = User.objects.create_user(
        username=username,
        password="x",
        domain="domain.com",
        locale="en",
        group_list=[{"id": g, "name": f"T{g}"} for g in group_ids],
        roles=["normal"],
    )
    user.is_superuser = False
    user.save()
    user.permission = permission  # 运行时属性,非模型字段
    return user


def _put(user, current_team, body, pk):
    factory = APIRequestFactory()
    request = factory.put("/", data=body, format="json")
    force_authenticate(request, user=user)
    request.COOKIES["current_team"] = str(current_team)
    view = BotViewSet.as_view({"put": "update"})
    return view(request, pk=pk)


class TestBotCreateExplicitUsageTeam:
    def test_create_with_explicit_usage_team_superset(self):
        """create 显式传 usage_team(含管理组织):原样保留为超集。"""
        resp = _post("create", _make_superuser(), 1, {"name": "cu1", "team": [1], "usage_team": [1, 2, 3]})
        assert resp.status_code == 200
        bot = Bot.objects.get(name="cu1")
        assert bot.team == [1]
        assert bot.usage_team == [1, 2, 3]

    def test_create_forces_management_org_into_usage_team(self):
        """create 显式 usage_team 未含管理组织:强制并入且管理组织在前。"""
        resp = _post("create", _make_superuser("bot_cu_su2"), 1, {"name": "cu2", "team": [1], "usage_team": [2]})
        assert resp.status_code == 200
        bot = Bot.objects.get(name="cu2")
        assert bot.usage_team == [1, 2]  # team ⊆ usage_team,管理组织 1 恒在且在前


class TestBotUpdateUsageTeam:
    def test_update_with_usage_team_adds_extra_orgs(self):
        bot = Bot.objects.create(name="uu1", team=[1], usage_team=[1])
        resp = _put(_make_superuser("bot_uu_su1"), 1, {"usage_team": [1, 2, 3]}, pk=bot.id)
        assert resp.status_code == 200
        bot.refresh_from_db()
        assert bot.usage_team == [1, 2, 3]

    def test_update_forces_management_org_into_usage_team(self):
        """update 请求体 usage_team 不含管理组织时强制并入(管理组织不可删)。"""
        bot = Bot.objects.create(name="uu2", team=[1], usage_team=[1, 2])
        resp = _put(_make_superuser("bot_uu_su2"), 1, {"usage_team": [2]}, pk=bot.id)
        assert resp.status_code == 200
        bot.refresh_from_db()
        assert bot.usage_team == [1, 2]

    def test_update_empty_usage_team_keeps_management_only(self):
        bot = Bot.objects.create(name="uu3", team=[1], usage_team=[1, 2, 3])
        resp = _put(_make_superuser("bot_uu_su3"), 1, {"usage_team": []}, pk=bot.id)
        assert resp.status_code == 200
        bot.refresh_from_db()
        assert bot.usage_team == [1]

    def test_update_team_only_maintains_invariant(self):
        """仅变更 team(请求体不含 usage_team)走 elif 分支:重新并入维持 team ⊆ usage_team。"""
        bot = Bot.objects.create(name="uu4", team=[1], usage_team=[1, 5])
        resp = _put(_make_superuser("bot_uu_su4"), 1, {"team": [1]}, pk=bot.id)
        assert resp.status_code == 200
        bot.refresh_from_db()
        # team 未实际变化,usage_team 经 _merge_usage_team(team, 旧 usage_team) 维持
        assert bot.usage_team == [1, 5]
        assert set(bot.team).issubset(set(bot.usage_team))


class TestBotUpdateTeamPermission:
    """update 时变更管理组织(team)必须校验目标组织权限,与 create 对齐(防越权改组)。"""

    def test_update_team_to_unauthorized_org_denied(self):
        """非超管把 team 改到自己无权管理的组织,应被拒绝(403)且 team 不被改动。"""
        bot = Bot.objects.create(name="tp1", team=[1], usage_team=[1])
        user = _make_normal_user("bot_tp_u1", [1], {"opspilot": {"bot_settings-Edit"}})
        # get_has_permission 走外部规则服务,这里 mock 放行 bot 当前 team 的编辑权,
        # 聚焦验证"新增的无权组织 99"被 _validate_org_field_permission 拦截。
        with patch.object(BotViewSet, "get_has_permission", return_value=True):
            resp = _put(user, 1, {"team": [1, 99]}, pk=bot.id)
        assert resp.status_code == 403
        bot.refresh_from_db()
        assert bot.team == [1]  # 校验失败,管理组织未被越权改动

    def test_update_team_to_authorized_org_allowed(self):
        """非超管把 team 改到自己有权管理的组织,应放行。"""
        bot = Bot.objects.create(name="tp2", team=[1], usage_team=[1])
        user = _make_normal_user("bot_tp_u2", [1, 2], {"opspilot": {"bot_settings-Edit"}})
        with patch.object(BotViewSet, "get_has_permission", return_value=True):
            resp = _put(user, 1, {"team": [1, 2]}, pk=bot.id)
        assert resp.status_code == 200
        bot.refresh_from_db()
        assert bot.team == [1, 2]

    def test_update_keeping_existing_unmanaged_org_allowed(self):
        """回归:保留既有(用户无权管理)的 team 组织、仅改其它字段时不应被误拦。

        team 校验应只针对【新增】组织(与 usage_team 分支一致);否则只管理 bot 部分组织的用户
        (get_has_permission 取交集即放行)连改名都会被全量校验误判 403。
        """
        bot = Bot.objects.create(name="tp3", team=[1, 2], usage_team=[1, 2])
        user = _make_normal_user("bot_tp_u3", [1], {"opspilot": {"bot_settings-Edit"}})
        with patch.object(BotViewSet, "get_has_permission", return_value=True):
            resp = _put(user, 1, {"name": "tp3-renamed", "team": [1, 2]}, pk=bot.id)
        assert resp.status_code == 200
        bot.refresh_from_db()
        assert bot.name == "tp3-renamed"
        assert bot.team == [1, 2]
