"""告警生命周期 Event 写入幂等规格。"""

from datetime import datetime, timezone

import pytest

from apps.monitor.models import MonitorAlert, MonitorEvent
from apps.monitor.services.alert_lifecycle_events import record_lifecycle_events

pytestmark = pytest.mark.django_db


def _alert(**kwargs):
    payload = dict(policy_id=1, monitor_instance_id="h1", status="new", content="cpu high")
    payload.update(kwargs)
    return MonitorAlert.objects.create(**payload)


class TestRecordLifecycleEvents:
    def test_writes_one_event_per_status_action(self):
        alert = _alert()
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        created = record_lifecycle_events(
            [alert],
            MonitorEvent.Action.TRIGGERED,
            event_time=now,
        )
        again = record_lifecycle_events(
            [alert],
            MonitorEvent.Action.TRIGGERED,
            event_time=now,
        )
        assert len(created) == 1
        assert again == []
        assert MonitorEvent.objects.filter(alert_id=alert.id, action=MonitorEvent.Action.TRIGGERED).count() == 1

    def test_closed_content_includes_operator_and_reason(self):
        alert = _alert()
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        created = record_lifecycle_events(
            [alert],
            MonitorEvent.Action.CLOSED,
            event_time=now,
            operator="admin",
            reason="manual",
        )
        assert created[0].action == MonitorEvent.Action.CLOSED
        assert "manual" in created[0].content
        assert "admin" in created[0].content
        assert record_lifecycle_events(
            [alert],
            MonitorEvent.Action.CLOSED,
            event_time=now,
            operator="admin",
            reason="manual",
        ) == []


def test_claimed_assigned_are_outside_status_unique_constraint():
    alert = _alert()
    for suffix in ("a", "b"):
        MonitorEvent.objects.create(
            id=f"claimed-{suffix}",
            alert=alert,
            policy_id=alert.policy_id,
            monitor_instance_id=alert.monitor_instance_id,
            level="warning",
            action=MonitorEvent.Action.CLAIMED,
            content="认领",
        )
        MonitorEvent.objects.create(
            id=f"assigned-{suffix}",
            alert=alert,
            policy_id=alert.policy_id,
            monitor_instance_id=alert.monitor_instance_id,
            level="warning",
            action=MonitorEvent.Action.ASSIGNED,
            content="分派",
        )
    assert MonitorEvent.objects.filter(alert=alert, action=MonitorEvent.Action.CLAIMED).count() == 2
    assert MonitorEvent.objects.filter(alert=alert, action=MonitorEvent.Action.ASSIGNED).count() == 2
