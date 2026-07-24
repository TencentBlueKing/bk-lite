from datetime import timedelta
from unittest import mock

import pytest
from django.db import transaction
from django.utils import timezone

from apps.alerts.models import AlertOutbox
from apps.alerts.service.outbox import deliver_outbox_record, enqueue_outbox


@pytest.mark.django_db(transaction=True)
def test_transaction_rollback_does_not_leave_outbox():
    with pytest.raises(RuntimeError):
        with transaction.atomic():
            enqueue_outbox("notification", {"params": []}, "rollback-key")
            raise RuntimeError("rollback")

    assert not AlertOutbox.objects.filter(idempotency_key="rollback-key").exists()


@pytest.mark.django_db(transaction=True)
def test_broker_failure_keeps_pending_outbox(django_capture_on_commit_callbacks):
    with mock.patch(
        "apps.alerts.tasks.deliver_alert_outbox.delay", side_effect=RuntimeError("broker down")
    ):
        with django_capture_on_commit_callbacks(execute=True):
            record, created = enqueue_outbox(
                "notification", {"params": [{"channel_id": 1}]}, "broker-key"
            )

    assert created is True
    record.refresh_from_db()
    assert record.status == AlertOutbox.Status.PENDING
    assert record.attempts == 0


@pytest.mark.django_db
def test_duplicate_idempotency_key_reuses_single_outbox():
    first, first_created = enqueue_outbox("action", {"alert_id": "A1"}, "same-key")
    second, second_created = enqueue_outbox("action", {"alert_id": "A1"}, "same-key")

    assert first_created is True
    assert second_created is False
    assert first.pk == second.pk
    assert AlertOutbox.objects.filter(idempotency_key="same-key").count() == 1


@pytest.mark.django_db(transaction=True)
def test_delivery_failure_is_retryable_then_marks_delivered():
    record = AlertOutbox.objects.create(
        kind="notification",
        payload={"params": [{"channel_id": 1}]},
        idempotency_key="retry-key",
    )

    with mock.patch("apps.alerts.service.outbox._deliver_payload", side_effect=RuntimeError("down")):
        with pytest.raises(RuntimeError):
            deliver_outbox_record(record.pk)

    record.refresh_from_db()
    assert record.status == AlertOutbox.Status.PENDING
    assert record.attempts == 1
    assert record.last_error == "down"
    assert record.next_retry_at is not None

    with mock.patch("apps.alerts.service.outbox._deliver_payload") as deliver:
        assert deliver_outbox_record(record.pk) is True

    deliver.assert_called_once()
    record.refresh_from_db()
    assert record.status == AlertOutbox.Status.DELIVERED
    assert record.delivered_at is not None


@pytest.mark.django_db
def test_dispatch_beat_reschedules_stale_delivering_outbox():
    """投递兜底节拍必须捞起卡死的 DELIVERING 行。

    worker 在投递中途崩溃/重启时行停留 DELIVERING;deliver_outbox_record 允许
    重投超过去重窗口的 DELIVERING 行,但 dispatch_pending_alert_outbox 此前只扫
    PENDING,导致这类行永久失联。
    """
    from apps.alerts.tasks.tasks import dispatch_pending_alert_outbox

    stale_time = timezone.now() - timedelta(minutes=10)

    pending = AlertOutbox.objects.create(
        kind="notification", payload={"params": []}, idempotency_key="k-pending"
    )
    stale_delivering = AlertOutbox.objects.create(
        kind="notification", payload={"params": []}, idempotency_key="k-stale-delivering",
        status=AlertOutbox.Status.DELIVERING, attempts=1,
    )
    # updated_at 为 auto_now,需用 update 回拨时间去重窗口之外
    AlertOutbox.objects.filter(pk=stale_delivering.pk).update(updated_at=stale_time)

    fresh_delivering = AlertOutbox.objects.create(
        kind="notification", payload={"params": []}, idempotency_key="k-fresh-delivering",
        status=AlertOutbox.Status.DELIVERING, attempts=1,
    )
    delivered = AlertOutbox.objects.create(
        kind="notification", payload={"params": []}, idempotency_key="k-delivered",
        status=AlertOutbox.Status.DELIVERED,
    )

    with mock.patch("apps.alerts.tasks.tasks.deliver_alert_outbox.delay") as delay:
        dispatch_pending_alert_outbox()

    scheduled = {call.args[0] for call in delay.call_args_list}
    assert pending.pk in scheduled
    assert stale_delivering.pk in scheduled
    assert fresh_delivering.pk not in scheduled  # 仍在去重窗口内,交给原投递流程
    assert delivered.pk not in scheduled
