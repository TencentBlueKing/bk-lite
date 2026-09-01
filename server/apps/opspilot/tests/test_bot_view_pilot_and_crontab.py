"""BotViewSet：usage_team 合并、crontab 预览、启停工作台。"""
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.tests.factories import UserFactory
from apps.opspilot.models import Bot, BotWorkFlow
from apps.opspilot.viewsets.bot_view import BotFilter, BotViewSet, _merge_usage_team, _schedule_memory_write_cache_flush

pytestmark = pytest.mark.django_db
factory = APIRequestFactory()


def _unwrap(fn):
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    return fn


def test_merge_usage_team_keeps_management_first_and_unique():
    assert _merge_usage_team([1], [1, 2, 1]) == [1, 2]
    assert _merge_usage_team([3, 1], [2]) == [3, 1, 2]
    assert _merge_usage_team([], [4]) == [4]
    assert _merge_usage_team(None, None) == []


def test_filter_bot_type_splits_and_ignores_empty():
    qs = SimpleNamespace(filter=lambda **kwargs: kwargs)
    assert BotFilter.filter_bot_type(qs, "bot_type", "") is qs
    out = BotFilter.filter_bot_type(qs, "bot_type", "1, 2,")
    assert out["bot_type__in"] == [1, 2]


def test_preview_crontab_requires_expression_and_caps_count():
    view = BotViewSet()
    view.loader = None
    fn = _unwrap(BotViewSet.preview_crontab)
    request_user = SimpleNamespace(timezone=None)
    empty = fn(view, SimpleNamespace(data={"crontab_expression": ""}, user=request_user))
    body = json.loads(empty.content)
    assert body["result"] is False
    with patch("apps.opspilot.viewsets.bot_view.get_crontab_next_runs", return_value=["2026-01-01 00:00:00"]) as preview:
        ok = fn(
            view,
            SimpleNamespace(
                data={"crontab_expression": "0 * * * *", "count": 99},
                user=request_user,
            ),
        )
    assert json.loads(ok.content)["result"] is True
    preview.assert_called_once()
    assert preview.call_args.kwargs["count"] == 20
    with patch("apps.opspilot.viewsets.bot_view.get_crontab_next_runs", side_effect=ValueError("bad")):
        bad = fn(
            view,
            SimpleNamespace(
                data={"crontab_expression": "not a cron"},
                user=request_user,
            ),
        )
    assert json.loads(bad.content)["result"] is False


def test_start_and_stop_pilot_superuser_toggles_online():
    user = UserFactory(username="bot-admin", domain="domain.com", roles=[], is_superuser=True)
    bot = Bot.objects.create(name="pilot-bot", team=[1], online=False, api_token="")
    BotWorkFlow.objects.create(bot=bot, flow_json={"nodes": []}, web_json={"nodes": []})
    view = BotViewSet.as_view({"post": "start_pilot"})
    req = factory.post("/start_pilot/", {"bot_ids": [bot.id]}, format="json")
    force_authenticate(req, user=user)
    req.COOKIES["current_team"] = "1"
    with (
        patch("apps.opspilot.viewsets.bot_view.create_celery_task"),
        patch("apps.opspilot.viewsets.bot_view.sync_opspilot_nats_channels_for_bot"),
        patch("apps.opspilot.viewsets.bot_view.log_operation"),
    ):
        resp = view(req)
    assert json.loads(resp.content)["result"] is True
    bot.refresh_from_db()
    assert bot.online is True
    assert bot.api_token

    stop = BotViewSet.as_view({"post": "stop_pilot"})
    req2 = factory.post("/stop_pilot/", {"bot_ids": [bot.id]}, format="json")
    force_authenticate(req2, user=user)
    req2.COOKIES["current_team"] = "1"
    with (
        patch("apps.opspilot.viewsets.bot_view.delete_celery_task"),
        patch("apps.opspilot.viewsets.bot_view.cleanup_opspilot_nats_channels_for_bot"),
        patch("apps.opspilot.viewsets.bot_view.log_operation"),
    ):
        resp2 = stop(req2)
    assert json.loads(resp2.content)["result"] is True
    bot.refresh_from_db()
    assert bot.online is False
    assert bot.api_token == ""


def test_schedule_memory_flush_uses_both_field_names():
    workflow = SimpleNamespace(id=9)
    old = {"nodes": [{"id": "n1", "data": {"config": {"memorySpace": 11, "title": "旧"}}}]}
    new = {"nodes": []}
    with patch(
        "apps.opspilot.viewsets.bot_view.find_memory_write_nodes_to_flush", return_value={"n1": {"memorySpace": 11, "title": "旧", "llmModel": 3}}
    ):
        with patch("apps.opspilot.viewsets.bot_view.flush_memory_write_cache_for_node") as task:
            _schedule_memory_write_cache_flush(workflow, old, new)
    task.delay.assert_called_once()
    assert task.delay.call_args.kwargs["memory_space_id"] == 11
    with patch("apps.opspilot.viewsets.bot_view.find_memory_write_nodes_to_flush", return_value={"n2": {"title": "无空间"}}):
        with patch("apps.opspilot.viewsets.bot_view.flush_memory_write_cache_for_node") as task2:
            _schedule_memory_write_cache_flush(workflow, old, new)
    task2.delay.assert_not_called()
