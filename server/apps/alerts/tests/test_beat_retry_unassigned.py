"""UNASSIGNED 兜底节拍测试。

对照 docs/superpowers/plans/2026-07-23-alert-unassigned-assignment-fix.md §4.2:
周期扫描仍未分派的告警重新入 auto_assignment outbox,覆盖"告警变 UNASSIGNED 后
没有新事件流入,主链路再无机会触发分派"的场景。
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.alerts.constants.constants import AlertStatus
from apps.alerts.models import AlertOutbox
from apps.alerts.models.models import Alert
from apps.alerts.tasks.tasks import UNASSIGNED_RETRY_BATCH, beat_retry_unassigned_assignment


def _make_alert(alert_id, status=AlertStatus.UNASSIGNED, **over):
    defaults = dict(
        alert_id=alert_id, level="0", title="t", content="c",
        fingerprint="fp-beat-" + alert_id, status=status,
        source_name="prometheus", team=[1],
    )
    defaults.update(over)
    return Alert(**defaults)


@pytest.mark.django_db
def test_beat_retry_enqueues_unassigned_alerts_only():
    """未分派普通/已确认会话告警入队；已分派和观察期会话告警排除。"""
    Alert.objects.bulk_create([
        _make_alert("A-1"),
        _make_alert("A-2"),
        _make_alert("A-3", status=AlertStatus.PENDING),
        _make_alert("A-4", status=AlertStatus.PROCESSING),
        _make_alert("A-5", is_session_alert=True, session_status="confirmed"),
        _make_alert("A-6", is_session_alert=True, session_status="observing"),
    ])

    result = beat_retry_unassigned_assignment()

    assert result == {"retried": 3}
    record = AlertOutbox.objects.get(kind="auto_assignment")
    alert_ids = record.payload["alert_ids"]
    assert set(alert_ids) == {"A-1", "A-2", "A-5"}


@pytest.mark.django_db
def test_beat_retry_no_candidates():
    result = beat_retry_unassigned_assignment()

    assert result == {"retried": 0}
    assert not AlertOutbox.objects.filter(kind="auto_assignment").exists()


@pytest.mark.django_db
def test_beat_retry_is_idempotent():
    """候选集合不变时重跑不产生重复 outbox 记录(idempotency_key 防重)。"""
    Alert.objects.bulk_create([_make_alert("A-1")])

    first = beat_retry_unassigned_assignment()
    second = beat_retry_unassigned_assignment()

    assert first == {"retried": 1}
    assert second == {"retried": 0}
    assert AlertOutbox.objects.filter(kind="auto_assignment").count() == 1


@pytest.mark.django_db
def test_beat_retry_respects_batch_limit():
    Alert.objects.bulk_create(
        [_make_alert(f"A-{i}") for i in range(UNASSIGNED_RETRY_BATCH + 5)]
    )

    result = beat_retry_unassigned_assignment()

    assert result == {"retried": UNASSIGNED_RETRY_BATCH}
    record = AlertOutbox.objects.get(kind="auto_assignment")
    assert len(record.payload["alert_ids"]) == UNASSIGNED_RETRY_BATCH


@pytest.mark.django_db
def test_beat_retry_next_window_advances_past_still_unassigned_first_batch(mocker):
    """首批 0 命中仍为 UNASSIGNED 时，下一周期必须继续处理后续候选。"""
    Alert.objects.bulk_create(
        [_make_alert(f"A-{i:03d}") for i in range(UNASSIGNED_RETRY_BATCH + 5)]
    )
    first_window = timezone.now().replace(second=0, microsecond=0)
    clock = {"now": first_window}
    mocker.patch("apps.alerts.tasks.tasks.timezone.now", side_effect=lambda: clock["now"])

    first = beat_retry_unassigned_assignment()
    first_record = AlertOutbox.objects.get(kind="auto_assignment")
    first_record.status = AlertOutbox.Status.DELIVERED
    first_record.attempts = 1
    first_record.save(update_fields=["status", "attempts"])
    clock["now"] = first_window + timedelta(minutes=5)
    second = beat_retry_unassigned_assignment()

    records = list(AlertOutbox.objects.filter(kind="auto_assignment").order_by("pk"))
    assert first == {"retried": UNASSIGNED_RETRY_BATCH}
    assert second == {"retried": 5}
    assert len(records) == 2
    assert set(records[0].payload["alert_ids"]).isdisjoint(
        records[1].payload["alert_ids"]
    )
    assert {
        alert_id
        for record in records
        for alert_id in record.payload["alert_ids"]
    } == {f"A-{i:03d}" for i in range(UNASSIGNED_RETRY_BATCH + 5)}
