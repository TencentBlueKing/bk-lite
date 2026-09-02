"""BotViewSet 剩余动作：授权成功、destroy 审计、启停拒绝、日志/crontab 契约。

对照契约：authorize_usage_team 超管成功并入管理组织并记「授权使用组织」；
destroy 成功记「删除工作台」；非超管无编辑权拒绝更新/启停/看日志；
preview_crontab 缺表达式与非法表达式返回固定英文文案。
"""
import json
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.tests.factories import UserFactory
from apps.opspilot.models import Bot, BotWorkFlow, WorkFlowConversationHistory
from apps.opspilot.viewsets.bot_view import BotViewSet

pytestmark = pytest.mark.django_db
factory = APIRequestFactory()
MOD = "apps.opspilot.viewsets.bot_view"


def _su(name="bot-rem"):
    return UserFactory(
        username=f"{name}-{uuid.uuid4().hex[:8]}",
        domain="domain.com",
        roles=[],
        is_superuser=True,
        group_list=[{"id": 1, "name": "T1"}, {"id": 2, "name": "T2"}],
    )


def _guest(perm):
    user = UserFactory(
        username=f"bot-guest-{uuid.uuid4().hex[:8]}",
        domain="domain.com",
        roles=[],
        is_superuser=False,
        group_list=[{"id": 1, "name": "T1"}],
    )
    user.permission = {"opspilot": perm}
    return user


def _body(resp):
    if hasattr(resp, "content"):
        try:
            return json.loads(resp.content.decode("utf-8"))
        except Exception:
            pass
    return getattr(resp, "data", None)


def _unwrap(fn):
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    return fn


def test_authorize_usage_team_success_merges_and_logs():
    user = _su("bot-auth-ok")
    bot = Bot.objects.create(name="授权台", team=[1], usage_team=[1])
    req = factory.post(f"/{bot.id}/authorize_usage_team/", {"usage_team": [2]}, format="json")
    force_authenticate(req, user=user)
    req.COOKIES["current_team"] = "1"
    with patch(f"{MOD}.log_operation") as log:
        resp = BotViewSet.as_view({"post": "authorize_usage_team"})(req, pk=bot.id)
    assert resp.status_code == 200
    assert _body(resp) == {"result": True, "data": {"usage_team": [1, 2]}}
    bot.refresh_from_db()
    assert bot.usage_team == [1, 2]
    assert bot.updated_by == user.username
    log.assert_called_once()
    assert log.call_args.args[-1] == "授权使用组织: 授权台"


def test_destroy_logs_bot_name():
    user = _su("bot-del-log")
    bot = Bot.objects.create(name="待删台", team=[1])
    BotWorkFlow.objects.create(bot=bot, flow_json={}, web_json={})
    req = factory.delete(f"/{bot.id}/")
    force_authenticate(req, user=user)
    req.COOKIES["current_team"] = "1"
    with (
        patch(f"{MOD}.delete_celery_task"),
        patch(f"{MOD}.cleanup_opspilot_nats_channels_for_bot"),
        patch(f"{MOD}.log_operation") as log,
    ):
        resp = BotViewSet.as_view({"delete": "destroy"})(req, pk=bot.id)
    assert resp.status_code == 204
    assert not Bot.objects.filter(id=bot.id).exists()
    assert any(c.args[-1] == "删除工作台: 待删台" for c in log.call_args_list)


def test_update_and_start_stop_denied_for_non_owner():
    user = _guest({"bot_settings-Edit", "bot_settings-Save&Publish"})
    bot = Bot.objects.create(name="锁台", team=[1], online=False)
    BotWorkFlow.objects.create(bot=bot, flow_json={}, web_json={})

    upd = factory.put(f"/{bot.id}/", {"name": "改名"}, format="json")
    force_authenticate(upd, user=user)
    upd.COOKIES["current_team"] = "1"
    with patch.object(BotViewSet, "get_has_permission", return_value=False):
        denied_upd = BotViewSet.as_view({"put": "update"})(upd, pk=bot.id)
    assert _body(denied_upd) == {"result": False, "message": "You do not have permission to update this bot."}

    start = factory.post("/start_pilot/", {"bot_ids": [bot.id]}, format="json")
    force_authenticate(start, user=user)
    start.COOKIES["current_team"] = "1"
    with patch.object(BotViewSet, "get_has_permission", return_value=False):
        denied_start = BotViewSet.as_view({"post": "start_pilot"})(start)
    assert _body(denied_start) == {"result": False, "message": "You do not have permission to start this bot."}

    stop = factory.post("/stop_pilot/", {"bot_ids": [bot.id]}, format="json")
    force_authenticate(stop, user=user)
    stop.COOKIES["current_team"] = "1"
    with patch.object(BotViewSet, "get_has_permission", return_value=False):
        denied_stop = BotViewSet.as_view({"post": "stop_pilot"})(stop)
    assert _body(denied_stop) == {"result": False, "message": "You do not have permission to stop this bot"}


def test_search_and_detail_log_denied_without_bot_id_uses_history():
    user = _guest({"bot_conversation_log-View"})
    bot = Bot.objects.create(name="日志台", team=[1])
    now = timezone.now()
    h = WorkFlowConversationHistory.objects.create(
        bot_id=bot.id,
        node_id="n1",
        user_id="alice",
        conversation_role="user",
        conversation_content="hello",
        conversation_time=now,
        entry_type="web_chat",
        session_id="s1",
    )

    view = BotViewSet()
    view.loader = None
    search = SimpleNamespace(
        GET={"bot_id": str(bot.id)},
        user=user,
        COOKIES={"current_team": "1"},
    )
    with (
        patch.object(BotViewSet, "_validate_current_team_permission", return_value=1),
        patch.object(BotViewSet, "get_has_permission", return_value=False),
    ):
        denied_search = _unwrap(BotViewSet.search_workflow_log)(view, search)
    assert _body(denied_search) == {"result": False, "message": "You do not have permission to view this bot."}

    detail = SimpleNamespace(
        data={"ids": [h.id], "page": 1, "page_size": 10},
        user=user,
        COOKIES={"current_team": "1"},
    )
    with (
        patch.object(BotViewSet, "_validate_current_team_permission", return_value=1),
        patch.object(BotViewSet, "get_has_permission", return_value=False),
    ):
        denied_detail = _unwrap(BotViewSet.get_workflow_log_detail)(view, detail)
    assert _body(denied_detail) == {"result": False, "message": "You do not have permission to view this bot."}


def test_preview_crontab_locks_required_and_invalid_messages():
    view = BotViewSet()
    view.loader = None
    fn = _unwrap(BotViewSet.preview_crontab)
    request_user = SimpleNamespace(timezone=None)
    empty = fn(view, SimpleNamespace(data={"crontab_expression": ""}, user=request_user))
    assert json.loads(empty.content.decode("utf-8")) == {
        "result": False,
        "message": "crontab_expression is required",
    }
    with patch(f"{MOD}.get_crontab_next_runs", side_effect=ValueError("bad")):
        bad = fn(
            view,
            SimpleNamespace(
                data={"crontab_expression": "not a cron"},
                user=request_user,
            ),
        )
    assert json.loads(bad.content.decode("utf-8")) == {
        "result": False,
        "message": "Invalid crontab expression: not a cron",
    }
