from datetime import datetime, timezone
from types import SimpleNamespace

from apps.log.nats.log import _build_paginated_alert_segments


class FakeAlertQuerySet:
    def __init__(self, alerts):
        self.alerts = alerts
        self.sliced = None

    def count(self):
        return len(self.alerts)

    def order_by(self, *fields):
        return self

    def __getitem__(self, value):
        self.sliced = value
        return self.alerts[value]


def make_alert(alert_id):
    event_time = datetime(2026, 5, 6, 1, alert_id, tzinfo=timezone.utc)
    return SimpleNamespace(
        id=alert_id,
        policy_id="policy-1",
        collect_type_id="ctype-1",
        source_id=f"source-{alert_id}",
        level="warning",
        value="1",
        content="content",
        status="active",
        start_event_time=event_time,
        end_event_time=event_time,
        created_at=event_time,
        updated_at=event_time,
    )


def test_alert_segments_are_sliced_before_building_response_items():
    queryset = FakeAlertQuerySet([make_alert(idx) for idx in range(1, 6)])

    result = _build_paginated_alert_segments(queryset, page=2, page_size=2)

    assert queryset.sliced == slice(2, 4, None)
    assert result["count"] == 5
    assert [item["id"] for item in result["items"]] == [3, 4]
