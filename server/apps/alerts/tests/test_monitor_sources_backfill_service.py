"""监控源历史回填不改变告警状态、排序时间或触发通知。"""

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.alerts.models import Alert, AlertOutbox, AlertSource, Event

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_backfill_supports_dry_run_batches_and_repeated_execution():
    source = AlertSource.objects.create(name="历史", source_id="historical-sources", source_type="nats", secret="test")
    first = Event.objects.create(
        source=source, event_id="old-1", title="CPU", level="1", start_time=timezone.now(), raw_data={}, push_source_id="prod"
    )
    second = Event.objects.create(
        source=source, event_id="old-2", title="CPU", level="1", start_time=timezone.now(), raw_data={}, push_source_id="test"
    )
    alerts = []
    for index in range(3):
        alert = Alert.objects.create(alert_id=f"old-{index}", title="CPU", content="", level="1", fingerprint=f"old-{index}", status="closed")
        alert.events.add(first, second)
        alerts.append(alert)
    output = StringIO()
    call_command("backfill_alert_monitor_sources", batch_size=1, dry_run=True, stdout=output)
    assert list(Alert.objects.values_list("push_source_ids", flat=True)) == [[], [], []]
    call_command("backfill_alert_monitor_sources", batch_size=1, stdout=output)
    for alert in alerts:
        previous_time = alert.updated_at
        alert.refresh_from_db()
        assert alert.push_source_ids == ["prod", "test"]
        assert alert.status == "closed"
        assert alert.updated_at == previous_time
    output = StringIO()
    call_command("backfill_alert_monitor_sources", batch_size=1, stdout=output)
    assert "updated=0" in output.getvalue()


@pytest.mark.parametrize("options", [{"batch_size": 0}, {"batch_size": 1001}, {"after_id": -1}])
def test_backfill_rejects_invalid_cursor_or_batch_size(options):
    with pytest.raises(CommandError):
        call_command("backfill_alert_monitor_sources", stdout=StringIO(), **options)


def test_backfill_empty_database_is_a_noop():
    output = StringIO()
    call_command("backfill_alert_monitor_sources", stdout=output)
    assert "scanned=0 updated=0 last_id=0" in output.getvalue()
    assert not AlertOutbox.objects.exists()


def historical_alerts():
    source = AlertSource.objects.create(name="续跑", source_id="resume-sources", source_type="restful", secret="test")
    event = Event.objects.create(
        source=source, event_id="resume-event", title="CPU", level="1", start_time=timezone.now(), raw_data={}, push_source_id="001"
    )
    alerts = []
    for index in range(3):
        alert = Alert.objects.create(
            alert_id=f"resume-{index}", title="CPU", content="", level="1", fingerprint=f"resume-{index}", push_source_ids=["stale"]
        )
        alert.events.add(event)
        alerts.append(alert)
    return alerts, event


def test_backfill_resumes_after_interrupted_output_without_touching_completed_rows():
    alerts, _ = historical_alerts()

    class BrokenOutput(StringIO):
        def write(self, message):
            if "dry_run=False" in message:
                raise OSError("test closed output pipe")
            return super().write(message)

    with pytest.raises(OSError, match="closed output pipe"):
        call_command("backfill_alert_monitor_sources", batch_size=1, stdout=BrokenOutput())
    assert list(Alert.objects.order_by("pk").values_list("push_source_ids", flat=True)) == [["001"], ["stale"], ["stale"]]
    previous_times = list(Alert.objects.order_by("pk").values_list("updated_at", flat=True))
    output = StringIO()
    call_command("backfill_alert_monitor_sources", batch_size=1, after_id=alerts[0].pk, stdout=output)
    assert "scanned=2 updated=2" in output.getvalue()
    assert list(Alert.objects.order_by("pk").values_list("push_source_ids", flat=True)) == [["001"], ["001"], ["001"]]
    assert list(Alert.objects.order_by("pk").values_list("updated_at", flat=True)) == previous_times
    assert not AlertOutbox.objects.exists()


def test_backfill_uses_fixed_upper_bound_and_handles_deletion_between_pages():
    alerts, event = historical_alerts()
    appended = []

    class ChangingOutput(StringIO):
        def write(self, message):
            if "dry_run=False" in message and not appended:
                alerts[1].delete()
                alerts[2].events.clear()
                added = Alert.objects.create(alert_id="after-start", title="new", content="", level="1", fingerprint="new")
                added.events.add(event)
                appended.append(added)
            return super().write(message)

    output = ChangingOutput()
    call_command("backfill_alert_monitor_sources", batch_size=1, stdout=output)
    assert "scanned=2 updated=2" in output.getvalue()
    assert list(Alert.objects.order_by("pk").values_list("push_source_ids", flat=True)) == [["001"], [], []]
    # 运行中新增记录留待下一轮；无关联事件的陈旧快照清空。
    output = StringIO()
    call_command("backfill_alert_monitor_sources", batch_size=1, stdout=output)
    appended[0].refresh_from_db()
    assert appended[0].push_source_ids == ["001"]
    assert "scanned=3 updated=1" in output.getvalue()
    assert not AlertOutbox.objects.exists()
