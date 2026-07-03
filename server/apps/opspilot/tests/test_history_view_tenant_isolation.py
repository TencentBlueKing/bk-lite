"""Tests for tenant isolation in HistoryViewSet.get_log_detail.

Issue #3432: get_log_detail 按任意 ids 读取对话内容，无租户归属校验可跨租户枚举对话历史。

The fix adds `bot__team__contains=[current_team]` to the ORM filter in get_log_detail,
ensuring users can only retrieve conversation history records belonging to their current team.

These tests verify:
- A user in team 1 cannot retrieve records from a bot belonging to team 2 (cross-tenant blocked).
- A user in team 1 can retrieve records from their own bot (same-team allowed).
- Reverting the fix (removing the team filter) causes the cross-tenant test to fail (revert-fail criterion met).
"""

import json
from unittest.mock import MagicMock

import pytest


pytestmark = pytest.mark.django_db


def _make_request(request_factory, body, current_team, user=None):
    """Build a POST request with cookies for current_team."""
    req = request_factory.post(
        "/api/v1/opspilot/bot_mgmt/history/get_log_detail/",
        data=json.dumps(body),
        content_type="application/json",
    )
    req.COOKIES["current_team"] = str(current_team)
    # 视图通过 DRF 的 request.data 读取请求体；这里用 RequestFactory 构造的是 WSGIRequest，
    # 没有 .data，直接挂上解析后的 body 以驱动真实视图逻辑。
    req.data = body
    if user is None:
        user = MagicMock()
        user.is_superuser = False
        user.group_list = [{"id": current_team}]
        # get_log_detail 受 @HasPermission("bot_conversation_log-View") 保护，
        # 授予对应权限以放行到真正的租户隔离逻辑（否则被 403 拦在外层）。
        user.permission = {"opspilot": {"bot_conversation_log-View"}}
    req.user = user
    return req


def _make_get_request(request_factory, params, current_team, user=None):
    """Build a GET request with cookies for current_team."""
    req = request_factory.get(
        "/api/v1/opspilot/bot_mgmt/history/get_tag_detail/",
        data=params,
    )
    req.COOKIES["current_team"] = str(current_team)
    if user is None:
        user = MagicMock()
        user.is_superuser = False
        user.group_list = [{"id": current_team}]
        user.permission = {"opspilot": {"bot_conversation_log-View"}}
    req.user = user
    return req


class TestGetLogDetailTenantIsolation:
    """get_log_detail 必须按 current_team 做租户隔离（Issue #3432）。

    使用真实 DB 模型验证：bot__team__contains=[current_team] 过滤生效，
    跨租户 bot 的对话记录不可被枚举，同租户记录可正常读取。
    """

    def _make_bot(self, team_ids):
        from apps.opspilot.models import Bot

        return Bot.objects.create(name=f"bot-{team_ids}", team=team_ids, usage_team=team_ids)

    def _make_history(self, bot, role, text):
        from apps.opspilot.models import BotConversationHistory

        return BotConversationHistory.objects.create(bot=bot, conversation_role=role, conversation=text)

    def test_cross_tenant_records_are_excluded(self, request_factory):
        """team=1 用户请求属于 team=[2] 的 bot 记录，必须返回空（不泄漏）。"""
        from apps.opspilot.viewsets.history_view import HistoryViewSet

        other_bot = self._make_bot([2])
        h1 = self._make_history(other_bot, "user", "secret msg")
        h2 = self._make_history(other_bot, "bot", "secret answer")

        request = _make_request(request_factory, body={"ids": [h1.id, h2.id]}, current_team=1)
        viewset = HistoryViewSet()
        viewset.format_kwarg = None

        response = viewset.get_log_detail(request)
        data = json.loads(response.content)

        assert data["result"] is True
        assert data["data"] == [], "跨租户记录不得返回"

    def test_same_tenant_records_are_returned(self, request_factory):
        """team=1 用户请求属于 team=[1] 的 bot 记录，必须正常返回。"""
        from apps.opspilot.viewsets.history_view import HistoryViewSet

        my_bot = self._make_bot([1])
        h1 = self._make_history(my_bot, "user", "hello")
        h2 = self._make_history(my_bot, "bot", "hi there")

        request = _make_request(request_factory, body={"ids": [h1.id, h2.id]}, current_team=1)
        viewset = HistoryViewSet()
        viewset.format_kwarg = None

        response = viewset.get_log_detail(request)
        data = json.loads(response.content)

        assert data["result"] is True
        assert len(data["data"]) == 2, "同租户记录必须可访问"
        contents = {row["content"] for row in data["data"]}
        assert contents == {"hello", "hi there"}
        roles = {row["role"] for row in data["data"]}
        assert roles == {"user", "bot"}

    def test_mixed_ids_only_returns_own_team_records(self, request_factory):
        """同时请求本租户与他租户 ids 时，只返回本租户记录。"""
        from apps.opspilot.viewsets.history_view import HistoryViewSet

        my_bot = self._make_bot([1])
        other_bot = self._make_bot([2])
        mine = self._make_history(my_bot, "user", "mine")
        theirs = self._make_history(other_bot, "user", "theirs")

        request = _make_request(request_factory, body={"ids": [mine.id, theirs.id]}, current_team=1)
        viewset = HistoryViewSet()
        viewset.format_kwarg = None

        response = viewset.get_log_detail(request)
        data = json.loads(response.content)

        assert data["result"] is True
        returned_ids = {row["id"] for row in data["data"]}
        assert returned_ids == {mine.id}

    def test_no_current_team_cookie_is_rejected(self, request_factory):
        """缺少有效 current_team 时，权限校验抛 PermissionDenied。"""
        from rest_framework.exceptions import PermissionDenied

        from apps.opspilot.viewsets.history_view import HistoryViewSet

        my_bot = self._make_bot([1])
        h1 = self._make_history(my_bot, "user", "hello")

        request = _make_request(request_factory, body={"ids": [h1.id]}, current_team=0)
        viewset = HistoryViewSet()
        viewset.format_kwarg = None

        with pytest.raises(PermissionDenied):
            viewset.get_log_detail(request)


class TestGetTagDetailTenantIsolation:
    """get_tag_detail 必须按 ConversationTag.answer.bot.team 做租户隔离（Issue #3438）。"""

    def _make_bot(self, team_ids):
        from apps.opspilot.models import Bot

        return Bot.objects.create(name=f"bot-{team_ids}", team=team_ids, usage_team=team_ids)

    def _make_history(self, bot, role, text):
        from apps.opspilot.models import BotConversationHistory

        return BotConversationHistory.objects.create(bot=bot, conversation_role=role, conversation=text)

    def _make_tag(self, history, question, content, knowledge_base_id=10):
        from apps.opspilot.models import ConversationTag

        return ConversationTag.objects.create(
            answer=history,
            question=question,
            content=content,
            knowledge_base_id=knowledge_base_id,
            knowledge_document_id=20,
        )

    def test_cross_tenant_tag_returns_404(self, request_factory):
        """team=1 用户用其他租户 tag_id 查询时，必须 404 且不泄漏标注内容。"""
        from django.http import Http404

        from apps.opspilot.viewsets.history_view import HistoryViewSet

        other_bot = self._make_bot([2])
        answer = self._make_history(other_bot, "bot", "secret answer")
        tag = self._make_tag(answer, "secret question", "secret content")

        request = _make_get_request(request_factory, params={"tag_id": tag.id}, current_team=1)
        viewset = HistoryViewSet()
        viewset.format_kwarg = None

        with pytest.raises(Http404):
            viewset.get_tag_detail(request)

    def test_same_tenant_tag_is_returned(self, request_factory):
        """team=1 用户查询本租户 tag_id 时，正常返回标注详情。"""
        from apps.opspilot.viewsets.history_view import HistoryViewSet

        my_bot = self._make_bot([1])
        answer = self._make_history(my_bot, "bot", "answer")
        tag = self._make_tag(answer, "question", "content", knowledge_base_id=99)

        request = _make_get_request(request_factory, params={"tag_id": tag.id}, current_team=1)
        viewset = HistoryViewSet()
        viewset.format_kwarg = None

        response = viewset.get_tag_detail(request)
        data = json.loads(response.content)

        assert data == {
            "result": True,
            "data": {
                "knowledge_base_id": 99,
                "content": "content",
                "question": "question",
            },
        }

    def test_unknown_tag_returns_404(self, request_factory):
        """不存在的 tag_id 和非本租户 tag_id 一样返回 404，避免存在性枚举。"""
        from django.http import Http404

        from apps.opspilot.viewsets.history_view import HistoryViewSet

        request = _make_get_request(request_factory, params={"tag_id": 999999}, current_team=1)
        viewset = HistoryViewSet()
        viewset.format_kwarg = None

        with pytest.raises(Http404):
            viewset.get_tag_detail(request)
