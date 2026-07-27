from unittest import mock

import pytest
from django.db import transaction

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
