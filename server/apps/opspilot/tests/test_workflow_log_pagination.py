from datetime import datetime, timezone

from apps.opspilot.viewsets.bot_view import BotViewSet


class _HistoryQuery:
    def __init__(self, rows):
        self.rows = rows
        self.order_by_args = None
        self.values_args = None

    def order_by(self, *args):
        self.order_by_args = args
        return self

    def values(self, *args):
        self.values_args = args
        return self.rows


def test_workflow_log_pagination_batches_history_lookup(mocker):
    day = datetime(2026, 6, 29, tzinfo=timezone.utc)
    later = datetime(2026, 6, 29, 9, 0, tzinfo=timezone.utc)
    earlier = datetime(2026, 6, 29, 8, 0, tzinfo=timezone.utc)
    other = datetime(2026, 6, 29, 10, 0, tzinfo=timezone.utc)
    entries = [
        {
            "day": day,
            "bot_id": 1,
            "user_id": "alice",
            "entry_type": "web_chat",
            "count": 2,
            "earliest_created_at": earlier,
            "last_updated_at": later,
        },
        {
            "day": day,
            "bot_id": 1,
            "user_id": "bob",
            "entry_type": "restful",
            "count": 1,
            "earliest_created_at": other,
            "last_updated_at": other,
        },
    ]
    ids_rows = [
        {
            "id": 2,
            "bot_id": 1,
            "user_id": "alice",
            "entry_type": "web_chat",
            "conversation_time": later,
        },
        {
            "id": 1,
            "bot_id": 1,
            "user_id": "alice",
            "entry_type": "web_chat",
            "conversation_time": earlier,
        },
        {
            "id": 3,
            "bot_id": 1,
            "user_id": "bob",
            "entry_type": "restful",
            "conversation_time": other,
        },
    ]
    title_rows = [
        {
            "bot_id": 1,
            "user_id": "alice",
            "conversation_time": later,
            "conversation_content": "newer alice message",
        },
        {
            "bot_id": 1,
            "user_id": "alice",
            "conversation_time": earlier,
            "conversation_content": "earliest alice title",
        },
        {
            "bot_id": 1,
            "user_id": "bob",
            "conversation_time": other,
            "conversation_content": "bob title",
        },
    ]
    ids_query = _HistoryQuery(ids_rows)
    title_query = _HistoryQuery(title_rows)
    history_filter = mocker.patch(
        "apps.opspilot.viewsets.bot_view.WorkFlowConversationHistory.objects.filter",
        side_effect=[ids_query, title_query],
    )

    _, result = BotViewSet._get_workflow_log_by_page(entries, page=1, page_size=10)

    assert history_filter.call_count == 2
    history_filter.assert_any_call(
        bot_id__in={1},
        user_id__in={"alice", "bob"},
        entry_type__in={"web_chat", "restful"},
        conversation_time__date__in={day.date()},
    )
    history_filter.assert_any_call(
        bot_id__in={1},
        user_id__in={"alice", "bob"},
        conversation_time__date__in={day.date()},
    )
    assert ids_query.order_by_args == ("-conversation_time",)
    assert ids_query.values_args == ("id", "bot_id", "user_id", "entry_type", "conversation_time")
    assert title_query.order_by_args == ("-conversation_time",)
    assert title_query.values_args == ("bot_id", "user_id", "conversation_time", "conversation_content")
    assert result[0]["ids"] == [2, 1]
    assert result[0]["title"] == "earliest alice title"
    assert result[1]["ids"] == [3]
    assert result[1]["title"] == "bob title"
