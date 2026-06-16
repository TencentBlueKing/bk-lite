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
from unittest.mock import MagicMock, patch

import pytest


pytestmark = pytest.mark.django_db


def _make_request(request_factory, body, current_team, user=None):
    """Build a POST request with cookies for current_team."""
    from django.test import RequestFactory

    req = request_factory.post(
        "/api/v1/opspilot/bot_mgmt/history/get_log_detail/",
        data=json.dumps(body),
        content_type="application/json",
    )
    req.COOKIES["current_team"] = str(current_team)
    if user is None:
        user = MagicMock()
        user.is_superuser = False
        user.group_list = [{"id": current_team}]
    req.user = user
    return req


class TestGetLogDetailTenantIsolation:
    """Verify that get_log_detail respects tenant (team) isolation."""

    def _setup_history_record(self, bot_team_ids, record_ids_to_create=None):
        """
        Create in-memory Bot and BotConversationHistory-like mock objects.
        Returns a tuple (bot_mock, history_qs_mock).
        """
        from unittest.mock import MagicMock, patch
        return bot_team_ids

    def test_cross_tenant_records_are_excluded(self, request_factory):
        """
        A user in team=1 requesting ids=[10, 20] where those records belong to
        a bot with team=[2] must receive an empty result, not the actual records.

        If the fix is reverted (no bot__team__contains filter), BotConversationHistory
        .objects.filter(id__in=ids) would return records regardless of team, causing
        this test to fail.
        """
        from apps.opspilot.viewsets.history_view import HistoryViewSet

        # Simulate: records 10, 20 exist but belong to bot with team=[2]
        # User is in team=1
        current_team = 1
        other_team = 2

        # Mock BotConversationHistory queryset:
        # Without fix: filter(id__in=ids) returns records
        # With fix: filter(id__in=ids, bot__team__contains=[1]) returns empty
        mock_history_in_other_team = [
            {"id": 10, "conversation_role": "user", "conversation": "secret msg", "citing_knowledge": []},
            {"id": 20, "conversation_role": "bot", "conversation": "secret answer", "citing_knowledge": []},
        ]

        def mock_filter(**kwargs):
            # Simulate the ORM: only return records if team filter matches
            qs = MagicMock()
            team_filter = kwargs.get("bot__team__contains")
            if team_filter is not None and other_team not in team_filter:
                # Team filter applied and other_team not in requested team -> empty
                qs.__iter__ = MagicMock(return_value=iter([]))
                qs.values.return_value = qs
                qs.order_by.return_value = qs
                qs.__len__ = MagicMock(return_value=0)
                qs.count = 0
                # Make it iterable as empty for Paginator
                qs.__iter__ = MagicMock(return_value=iter([]))
                empty_qs = MagicMock()
                empty_qs.__iter__ = MagicMock(return_value=iter([]))
                empty_qs.count = 0
                return empty_qs
            else:
                # No team filter or matching team -> leak (old behavior)
                qs.values.return_value = qs
                qs.order_by.return_value = qs
                qs.__iter__ = MagicMock(return_value=iter(mock_history_in_other_team))
                qs.count = 2
                return qs

        request = _make_request(request_factory, body={"ids": [10, 20]}, current_team=current_team)

        viewset = HistoryViewSet()
        viewset.format_kwarg = None

        with patch("apps.opspilot.viewsets.history_view.BotConversationHistory") as mock_model, \
             patch("apps.opspilot.viewsets.history_view.ConversationTag") as mock_tag:

            # Capture the actual filter call arguments to verify the fix
            captured_kwargs = {}

            def capturing_filter(**kwargs):
                captured_kwargs.update(kwargs)
                qs = MagicMock()
                team_filter = kwargs.get("bot__team__contains")
                if team_filter is not None and other_team not in team_filter:
                    # Correct: team filter excludes other-team records
                    empty_qs = MagicMock()
                    empty_qs.__iter__ = MagicMock(return_value=iter([]))
                    empty_qs.count = 0
                    vals = MagicMock()
                    vals.__iter__ = MagicMock(return_value=iter([]))
                    vals.count = 0
                    vals.__len__ = MagicMock(return_value=0)
                    ordered = MagicMock()
                    ordered.__iter__ = MagicMock(return_value=iter([]))
                    ordered.count = 0
                    ordered.__len__ = MagicMock(return_value=0)
                    vals.order_by = MagicMock(return_value=ordered)
                    qs.values = MagicMock(return_value=vals)
                    return qs
                else:
                    # No team filter — old behavior leaks data
                    vals = MagicMock()
                    vals.__iter__ = MagicMock(return_value=iter(mock_history_in_other_team))
                    ordered = MagicMock()
                    ordered.__iter__ = MagicMock(return_value=iter(mock_history_in_other_team))
                    ordered.count = 2
                    ordered.__len__ = MagicMock(return_value=2)
                    vals.order_by = MagicMock(return_value=ordered)
                    qs.values = MagicMock(return_value=vals)
                    return qs

            mock_model.objects.filter = capturing_filter
            mock_tag.objects.filter.return_value.values_list.return_value = []

            response = viewset.get_log_detail(request)

        response_data = json.loads(response.content)

        # The fix must have passed bot__team__contains=[current_team] to the filter
        assert "bot__team__contains" in captured_kwargs, (
            "Fix missing: get_log_detail must pass bot__team__contains to the ORM filter"
        )
        assert captured_kwargs["bot__team__contains"] == [current_team], (
            f"Expected bot__team__contains=[{current_team}], got {captured_kwargs.get('bot__team__contains')}"
        )

        # The response must be empty (no cross-tenant records leaked)
        assert response_data["result"] is True
        assert response_data["data"] == [], (
            "Cross-tenant records must not be returned — tenant isolation fix is missing"
        )

    def test_same_tenant_records_are_returned(self, request_factory):
        """
        A user in team=1 requesting ids that belong to a bot with team=[1]
        must receive the records normally.
        """
        from apps.opspilot.viewsets.history_view import HistoryViewSet

        current_team = 1
        records = [
            {"id": 5, "conversation_role": "user", "conversation": "hello", "citing_knowledge": []},
            {"id": 6, "conversation_role": "bot", "conversation": "hi there", "citing_knowledge": []},
        ]

        request = _make_request(request_factory, body={"ids": [5, 6]}, current_team=current_team)

        viewset = HistoryViewSet()
        viewset.format_kwarg = None

        with patch("apps.opspilot.viewsets.history_view.BotConversationHistory") as mock_model, \
             patch("apps.opspilot.viewsets.history_view.ConversationTag") as mock_tag:

            def same_team_filter(**kwargs):
                qs = MagicMock()
                team_filter = kwargs.get("bot__team__contains")
                # If team filter is present and matches team=1, return records
                if team_filter is None or current_team in team_filter:
                    vals = MagicMock()
                    ordered = MagicMock()
                    ordered.__iter__ = MagicMock(return_value=iter(records))
                    ordered.count = 2
                    ordered.__len__ = MagicMock(return_value=2)
                    vals.order_by = MagicMock(return_value=ordered)
                    qs.values = MagicMock(return_value=vals)
                else:
                    vals = MagicMock()
                    ordered = MagicMock()
                    ordered.__iter__ = MagicMock(return_value=iter([]))
                    ordered.count = 0
                    ordered.__len__ = MagicMock(return_value=0)
                    vals.order_by = MagicMock(return_value=ordered)
                    qs.values = MagicMock(return_value=vals)
                return qs

            mock_model.objects.filter = same_team_filter
            mock_tag.objects.filter.return_value.values_list.return_value = []

            response = viewset.get_log_detail(request)

        response_data = json.loads(response.content)
        assert response_data["result"] is True
        assert len(response_data["data"]) == 2, "Same-team records must be accessible"
        assert response_data["data"][0]["content"] == "hello"
        assert response_data["data"][1]["content"] == "hi there"
