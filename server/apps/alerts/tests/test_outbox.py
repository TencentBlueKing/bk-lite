from datetime import timedelta
from unittest import mock

import pytest
from django.db import transaction
from django.utils import timezone

from apps.alerts.extensions.outbox import outbox_handlers
from apps.alerts.models import AlertOutbox
from apps.alerts.service.outbox import _deliver_payload, _schedule_delivery, deliver_outbox_record, enqueue_outbox
from apps.alerts.tasks.tasks import dispatch_pending_alert_outbox


@pytest.fixture
def extension_handler():
    handler = mock.Mock()
    kind = "test.extension"
    outbox_handlers.register(kind, handler)
    yield kind, handler
    outbox_handlers._handlers.pop(kind, None)


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
def test_extension_outbox_uses_registered_scheduler(extension_handler):
    kind, handler = extension_handler
    record = AlertOutbox.objects.create(
        kind=kind,
        payload={"group_id": "group-1", "member_pks": [1]},
        idempotency_key="extension-schedule-key",
    )
    with mock.patch("apps.alerts.tasks.deliver_alert_outbox.delay") as shared:
        _schedule_delivery(record.pk)

    handler.schedule.assert_called_once_with(record.pk)
    shared.assert_not_called()


@pytest.mark.django_db
def test_duplicate_idempotency_key_reuses_single_outbox():
    first, first_created = enqueue_outbox("action", {"alert_id": "A1"}, "same-key")
    second, second_created = enqueue_outbox("action", {"alert_id": "A1"}, "same-key")

    assert first_created is True
    assert second_created is False
    assert first.pk == second.pk
    assert AlertOutbox.objects.filter(idempotency_key="same-key").count() == 1


def test_extension_outbox_kind_dispatches_to_registered_handler(extension_handler):
    kind, handler = extension_handler
    _deliver_payload(kind, {"group_id": "group-1"})

    handler.deliver.assert_called_once_with(
        {"group_id": "group-1"},
        delivery_claim=None,
    )


def test_unknown_extension_outbox_kind_is_rejected():
    with pytest.raises(ValueError, match="unsupported alert outbox kind"):
        _deliver_payload("test.extension.unknown", {"group_id": "group-1"})


def test_existing_outbox_kinds_keep_their_original_dispatch_contracts():
    with mock.patch("apps.alerts.tasks.action_tasks.process_alert_actions") as action:
        _deliver_payload("action", {"alert_id": "A1", "event_name": "created"})
    action.assert_called_once_with("A1", "created")

    with mock.patch("apps.alerts.tasks.tasks.async_auto_assignment_for_alerts") as assignment:
        _deliver_payload("auto_assignment", {"alert_ids": ["A1"]})
    assignment.assert_called_once_with(["A1"])


@pytest.mark.django_db(transaction=True)
def test_registered_notification_extension_keeps_original_delivery_contract():
    handler = mock.Mock()
    outbox_handlers.register("notification", handler)
    record = AlertOutbox.objects.create(
        kind="notification",
        payload={"params": [{"channel_id": 1}]},
        idempotency_key="notification-extension-contract",
    )
    try:
        assert deliver_outbox_record(record.pk) is True
    finally:
        outbox_handlers._handlers.pop("notification", None)

    handler.deliver.assert_called_once_with(
        {"params": [{"channel_id": 1}]},
        delivery_claim={"record_id": record.pk, "generation": 1},
    )
    assert not record.notification_deliveries.exists()


@pytest.mark.django_db(transaction=True)
def test_notification_outbox_materializes_every_selected_channel():
    record = AlertOutbox.objects.create(
        kind="notification",
        payload={"params": [{"channel_id": 1}, {"channel_id": 2}]},
        idempotency_key="notification-all-failed",
    )

    with mock.patch("apps.alerts.tasks.tasks.deliver_alert_notification_channel.delay") as delay:
        assert deliver_outbox_record(record.pk) is True

    record.refresh_from_db()
    deliveries = list(record.notification_deliveries.order_by("position"))
    assert record.status == AlertOutbox.Status.DELIVERED
    assert record.attempts == 1
    assert record.delivered_at is not None
    assert [delivery.channel_id for delivery in deliveries] == ["1", "2"]
    assert {call.args[0] for call in delay.call_args_list} == {
        delivery.pk for delivery in deliveries
    }


@pytest.mark.django_db(transaction=True)
def test_notification_outbox_hands_partial_delivery_to_channel_state_machine():
    record = AlertOutbox.objects.create(
        kind="notification",
        payload={"params": [{"channel_id": 1}, {"channel_id": 2}]},
        idempotency_key="notification-partial-success",
    )

    with mock.patch("apps.alerts.tasks.tasks.deliver_alert_notification_channel.delay") as delay:
        assert deliver_outbox_record(record.pk) is True

    record.refresh_from_db()
    assert record.status == AlertOutbox.Status.DELIVERED
    assert record.attempts == 1
    assert record.delivered_at is not None
    assert record.notification_deliveries.count() == 2
    assert delay.call_count == 2


def test_unknown_non_incident_outbox_kind_is_rejected():
    with pytest.raises(ValueError, match="unsupported alert outbox kind"):
        _deliver_payload("unknown", {})


@pytest.mark.django_db(transaction=True)
def test_delivery_failure_is_retryable_then_marks_delivered():
    record = AlertOutbox.objects.create(
        kind="action",
        payload={"alert_id": "A1", "event_name": "created"},
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


@pytest.mark.django_db(transaction=True)
def test_exhausted_extension_delivery_calls_hook_after_failed_state_is_committed(
    extension_handler,
):
    kind, handler = extension_handler
    record = AlertOutbox.objects.create(
        kind=kind,
        payload={"group_id": "1"},
        idempotency_key="exhausted-key",
        max_attempts=1,
    )

    def assert_failed_before_hook(kind, payload, error):
        record.refresh_from_db()
        assert record.status == AlertOutbox.Status.FAILED
        assert kind == "test.extension"
        assert payload == {"group_id": "1"}
        assert error == "timeout"

    handler.exhausted.side_effect = assert_failed_before_hook
    with mock.patch(
        "apps.alerts.service.outbox._deliver_payload", side_effect=RuntimeError("timeout")
    ):
        with pytest.raises(RuntimeError, match="timeout"):
            deliver_outbox_record(record.pk)

    handler.exhausted.assert_called_once()


@pytest.mark.django_db(transaction=True)
def test_non_exhausted_extension_failure_stays_pending_without_exhausted_hook(
    extension_handler,
):
    kind, handler = extension_handler
    record = AlertOutbox.objects.create(
        kind=kind,
        payload={"group_id": "1"},
        idempotency_key="not-exhausted-key",
        max_attempts=2,
    )

    with mock.patch(
        "apps.alerts.service.outbox._deliver_payload", side_effect=RuntimeError("timeout")
    ):
        with pytest.raises(RuntimeError, match="timeout"):
            deliver_outbox_record(record.pk)

    handler.exhausted.assert_not_called()
    record.refresh_from_db()
    assert record.status == AlertOutbox.Status.PENDING


@pytest.mark.django_db(transaction=True)
def test_exhausted_hook_failure_never_requeues_failed_outbox(extension_handler):
    kind, handler = extension_handler
    record = AlertOutbox.objects.create(
        kind=kind,
        payload={"group_id": "1"},
        idempotency_key="exhausted-hook-failure",
        max_attempts=1,
    )

    handler.exhausted.side_effect = RuntimeError("hook failed")
    with mock.patch(
        "apps.alerts.service.outbox._deliver_payload", side_effect=RuntimeError("timeout")
    ):
        with pytest.raises(RuntimeError, match="timeout"):
            deliver_outbox_record(record.pk)

    record.refresh_from_db()
    assert record.status == AlertOutbox.Status.FAILED
    assert record.attempts == 1


@pytest.mark.django_db(transaction=True)
def test_dispatcher_recovers_only_expired_delivering_lease_after_hard_crash():
    record = AlertOutbox.objects.create(
        kind="notification",
        payload={"params": []},
        idempotency_key="hard-crash-lease",
        status=AlertOutbox.Status.DELIVERING,
        attempts=1,
    )

    with mock.patch("apps.alerts.tasks.tasks.deliver_alert_outbox.delay") as delay:
        assert dispatch_pending_alert_outbox() == {"scheduled": 0}
    delay.assert_not_called()

    AlertOutbox.objects.filter(pk=record.pk).update(
        updated_at=timezone.now() - timedelta(minutes=6)
    )
    with mock.patch("apps.alerts.tasks.tasks.deliver_alert_outbox.delay") as delay:
        assert dispatch_pending_alert_outbox() == {"scheduled": 1}
    delay.assert_called_once_with(record.pk)

    with mock.patch("apps.alerts.service.outbox._deliver_payload"):
        assert deliver_outbox_record(record.pk) is True
    record.refresh_from_db()
    assert record.status == AlertOutbox.Status.DELIVERED
    assert record.attempts == 2


@pytest.mark.django_db(transaction=True)
def test_dispatcher_routes_extension_to_registered_scheduler(extension_handler):
    kind, handler = extension_handler
    record = AlertOutbox.objects.create(
        kind=kind,
        payload={"group_id": "group-1", "member_pks": [1]},
        idempotency_key="dispatcher-extension",
    )
    with mock.patch("apps.alerts.tasks.tasks.deliver_alert_outbox.delay") as shared:
        assert dispatch_pending_alert_outbox() == {"scheduled": 1}

    handler.schedule.assert_called_once_with(record.pk)
    shared.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_expired_exhausted_extension_lease_fails_once_without_redelivery(
    extension_handler,
):
    kind, handler = extension_handler
    record = AlertOutbox.objects.create(
        kind=kind,
        payload={"group_id": "1"},
        idempotency_key="expired-exhausted-incident",
        status=AlertOutbox.Status.DELIVERING,
        attempts=2,
        max_attempts=2,
    )
    AlertOutbox.objects.filter(pk=record.pk).update(
        updated_at=timezone.now() - timedelta(minutes=6)
    )

    def assert_failed_and_repeat_is_noop(kind, payload, error):
        record.refresh_from_db()
        assert record.status == AlertOutbox.Status.FAILED
        assert record.attempts == 2
        assert kind == "test.extension"
        assert payload == {"group_id": "1"}
        assert error == "delivery lease expired after retries exhausted"
        assert deliver_outbox_record(record.pk) is False

    handler.exhausted.side_effect = assert_failed_and_repeat_is_noop
    with mock.patch("apps.alerts.service.outbox._deliver_payload") as deliver:
        assert deliver_outbox_record(record.pk) is False
        assert deliver_outbox_record(record.pk) is False

    deliver.assert_not_called()
    handler.exhausted.assert_called_once()
    record.refresh_from_db()
    assert record.status == AlertOutbox.Status.FAILED
    assert record.attempts == 2


@pytest.mark.django_db(transaction=True)
def test_expired_exhausted_core_lease_fails_without_extension_hook(
    extension_handler,
):
    _, handler = extension_handler
    record = AlertOutbox.objects.create(
        kind="notification",
        payload={"params": []},
        idempotency_key="expired-exhausted-notification",
        status=AlertOutbox.Status.DELIVERING,
        attempts=1,
        max_attempts=1,
    )
    AlertOutbox.objects.filter(pk=record.pk).update(
        updated_at=timezone.now() - timedelta(minutes=6)
    )

    with mock.patch("apps.alerts.service.outbox._deliver_payload") as deliver:
        assert deliver_outbox_record(record.pk) is False

    deliver.assert_not_called()
    handler.exhausted.assert_not_called()
    record.refresh_from_db()
    assert record.status == AlertOutbox.Status.FAILED
    assert record.attempts == 1


@pytest.mark.django_db(transaction=True)
def test_expired_exhausted_extension_hook_failure_keeps_failed_state(
    extension_handler,
):
    kind, handler = extension_handler
    record = AlertOutbox.objects.create(
        kind=kind,
        payload={"group_id": "1"},
        idempotency_key="expired-exhausted-hook-failure",
        status=AlertOutbox.Status.DELIVERING,
        attempts=1,
        max_attempts=1,
    )
    AlertOutbox.objects.filter(pk=record.pk).update(
        updated_at=timezone.now() - timedelta(minutes=6)
    )

    handler.exhausted.side_effect = RuntimeError("hook failed")
    with mock.patch("apps.alerts.service.outbox._deliver_payload") as deliver:
        assert deliver_outbox_record(record.pk) is False

    deliver.assert_not_called()
    handler.exhausted.assert_called_once()
    record.refresh_from_db()
    assert record.status == AlertOutbox.Status.FAILED
    assert record.attempts == 1


@pytest.mark.django_db(transaction=True)
def test_expired_old_worker_failure_cannot_overwrite_new_worker_delivered_state(
    extension_handler,
):
    kind, handler = extension_handler
    record = AlertOutbox.objects.create(
        kind=kind,
        payload={"group_id": "1"},
        idempotency_key="fencing-delivered",
        max_attempts=3,
    )

    def old_worker_interleaving(_kind, _payload, **_kwargs):
        AlertOutbox.objects.filter(pk=record.pk).update(
            updated_at=timezone.now() - timedelta(minutes=6)
        )
        with mock.patch("apps.alerts.service.outbox._deliver_payload"):
            assert deliver_outbox_record(record.pk) is True
        raise RuntimeError("old worker failed after new worker delivered")

    with mock.patch(
        "apps.alerts.service.outbox._deliver_payload",
        side_effect=old_worker_interleaving,
    ):
        assert deliver_outbox_record(record.pk) is False

    handler.exhausted.assert_not_called()
    record.refresh_from_db()
    assert record.status == AlertOutbox.Status.DELIVERED
    assert record.attempts == 2


@pytest.mark.django_db(transaction=True)
def test_expired_old_worker_success_cannot_overwrite_new_worker_failed_state_or_repeat_hook(
    extension_handler,
):
    kind, handler = extension_handler
    record = AlertOutbox.objects.create(
        kind=kind,
        payload={"group_id": "1"},
        idempotency_key="fencing-failed",
        max_attempts=2,
    )

    def old_worker_interleaving(_kind, _payload, **_kwargs):
        AlertOutbox.objects.filter(pk=record.pk).update(
            updated_at=timezone.now() - timedelta(minutes=6)
        )
        with mock.patch(
            "apps.alerts.service.outbox._deliver_payload",
            side_effect=RuntimeError("new worker exhausted"),
        ):
            with pytest.raises(RuntimeError, match="new worker exhausted"):
                deliver_outbox_record(record.pk)

    with mock.patch(
        "apps.alerts.service.outbox._deliver_payload",
        side_effect=old_worker_interleaving,
    ):
        assert deliver_outbox_record(record.pk) is False

    handler.exhausted.assert_called_once()
    record.refresh_from_db()
    assert record.status == AlertOutbox.Status.FAILED
    assert record.attempts == 2
