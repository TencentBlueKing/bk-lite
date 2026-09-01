"""补齐告警自动恢复处理的公开行为。"""

from types import SimpleNamespace

import pytest

from apps.alerts.aggregation.recovery import auto_closer
from apps.alerts.constants.constants import AlertStatus, EventAction

pytestmark = pytest.mark.unit


class _Events:
    def __init__(self, events):
        self.events = events
        self.filters = []

    def filter(self, **kwargs):
        self.filters.append(kwargs)
        return self.events


def test_auto_closer_skips_unidentifiable_events_and_closes_all_matches(
    monkeypatch,
):
    saved = []
    alerts = [
        SimpleNamespace(
            alert_id="A-1",
            status="active",
            save=lambda **kwargs: saved.append(("A-1", kwargs)),
        ),
        SimpleNamespace(
            alert_id="A-2",
            status="active",
            save=lambda **kwargs: saved.append(("A-2", kwargs)),
        ),
    ]
    alert_query = SimpleNamespace(distinct=lambda: alerts)
    manager_calls = []

    def filter_alerts(**kwargs):
        manager_calls.append(kwargs)
        return alert_query

    monkeypatch.setattr(
        auto_closer.Alert,
        "objects",
        SimpleNamespace(filter=filter_alerts),
    )
    events = _Events(
        [
            SimpleNamespace(external_id=""),
            SimpleNamespace(external_id="incident-9"),
        ]
    )

    auto_closer.AutoCloser.handle_closed_events(events)

    assert events.filters == [{"action": EventAction.CLOSED}]
    assert manager_calls == [
        {
            "status__in": AlertStatus.ACTIVATE_STATUS,
            "events__external_id": "incident-9",
            "events__action": EventAction.CREATED,
        }
    ]
    assert [alert.status for alert in alerts] == [
        AlertStatus.AUTO_CLOSE,
        AlertStatus.AUTO_CLOSE,
    ]
    assert saved == [
        ("A-1", {"update_fields": ["status", "updated_at", "closed_at"]}),
        ("A-2", {"update_fields": ["status", "updated_at", "closed_at"]}),
    ]
