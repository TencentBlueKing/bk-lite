from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from apps.alerts.models import AlertNotificationDelivery, AlertOutbox
from apps.alerts.service.outbox import deliver_outbox_record
from apps.alerts.tasks.tasks import deliver_alert_notification_channel, dispatch_pending_alert_notification_deliveries


def _params():
    return [
        {
            "username_list": ["operator"],
            "channel_id": 11,
            "channel_type": "email",
            "title": "告警",
            "content": "邮件正文",
            "object_id": "A-100",
            "notify_action_object": "alert",
        },
        {
            "username_list": ["operator"],
            "channel_id": 22,
            "channel_type": "sms",
            "title": "告警",
            "content": "短信正文",
            "object_id": "A-100",
            "notify_action_object": "alert",
        },
    ]


@pytest.mark.django_db(transaction=True)
def test_notification_parent_materializes_channel_intents_before_marking_delivered():
    record = AlertOutbox.objects.create(
        kind="notification",
        payload={"params": _params()},
        idempotency_key="notification:phase2:materialize",
    )

    with mock.patch("apps.alerts.tasks.tasks.deliver_alert_notification_channel.delay") as delay:
        assert deliver_outbox_record(record.pk) is True

    record.refresh_from_db()
    deliveries = list(record.notification_deliveries.order_by("position"))
    assert record.status == AlertOutbox.Status.DELIVERED
    assert record.delivered_at is not None
    assert [(item.position, item.channel_type, item.channel_id) for item in deliveries] == [
        (0, "email", "11"),
        (1, "sms", "22"),
    ]
    assert all(item.status == AlertNotificationDelivery.Status.PENDING for item in deliveries)
    assert len({item.delivery_key for item in deliveries}) == 2
    assert deliveries[0].parameter == _params()[0]
    assert deliveries[1].parameter == _params()[1]
    assert {call.args[0] for call in delay.call_args_list} == {item.pk for item in deliveries}


@pytest.mark.django_db(transaction=True)
def test_partial_success_retries_only_failed_channel():
    record = AlertOutbox.objects.create(
        kind="notification",
        payload={"params": _params()},
        idempotency_key="notification:phase2:partial",
    )
    with mock.patch("apps.alerts.tasks.tasks.deliver_alert_notification_channel.delay"):
        assert deliver_outbox_record(record.pk) is True
    email, sms = list(record.notification_deliveries.order_by("position"))

    with mock.patch(
        "apps.alerts.tasks.tasks.sync_notify",
        side_effect=[[{"result": True}], [{"code": 500, "message": "sms unavailable"}]],
    ) as notify:
        deliver_alert_notification_channel(email.pk)
        deliver_alert_notification_channel(sms.pk)

    email.refresh_from_db()
    sms.refresh_from_db()
    assert email.status == AlertNotificationDelivery.Status.DELIVERED
    assert sms.status == AlertNotificationDelivery.Status.PENDING
    assert sms.attempts == 1
    assert sms.next_retry_at is not None
    assert "sms unavailable" in sms.last_error
    assert [call.args[0] for call in notify.call_args_list] == [[_params()[0]], [_params()[1]]]

    AlertNotificationDelivery.objects.filter(pk=sms.pk).update(next_retry_at=timezone.now() - timedelta(seconds=1))
    with mock.patch("apps.alerts.tasks.tasks.sync_notify", return_value=[{"result": True}]) as retry:
        deliver_alert_notification_channel(sms.pk)

    email.refresh_from_db()
    sms.refresh_from_db()
    assert email.attempts == 1
    assert sms.status == AlertNotificationDelivery.Status.DELIVERED
    assert sms.attempts == 2
    retry.assert_called_once_with([_params()[1]])


@pytest.mark.django_db(transaction=True)
def test_exhaustion_marks_only_failed_channel_terminal():
    record = AlertOutbox.objects.create(
        kind="notification",
        payload={"params": _params()},
        idempotency_key="notification:phase2:exhausted",
        max_attempts=1,
    )
    with mock.patch("apps.alerts.tasks.tasks.deliver_alert_notification_channel.delay"):
        assert deliver_outbox_record(record.pk) is True
    email, sms = list(record.notification_deliveries.order_by("position"))

    with mock.patch(
        "apps.alerts.tasks.tasks.sync_notify",
        side_effect=[[{"result": True}], [{"result": False, "message": "permanent"}]],
    ):
        deliver_alert_notification_channel(email.pk)
        deliver_alert_notification_channel(sms.pk)

    email.refresh_from_db()
    sms.refresh_from_db()
    record.refresh_from_db()
    assert record.status == AlertOutbox.Status.DELIVERED
    assert email.status == AlertNotificationDelivery.Status.DELIVERED
    assert sms.status == AlertNotificationDelivery.Status.FAILED
    assert sms.next_retry_at is None
    assert sms.last_error == "permanent"


@pytest.mark.django_db(transaction=True)
def test_explicit_non_retryable_failure_stops_immediately():
    record = AlertOutbox.objects.create(
        kind="notification",
        payload={"params": _params()[:1]},
        idempotency_key="notification:phase2:non-retryable",
    )
    with mock.patch("apps.alerts.tasks.tasks.deliver_alert_notification_channel.delay"):
        assert deliver_outbox_record(record.pk) is True
    delivery = record.notification_deliveries.get()

    with mock.patch(
        "apps.alerts.tasks.tasks.sync_notify",
        return_value=[
            {
                "result": False,
                "retryable": False,
                "message": "receiver does not exist",
            }
        ],
    ):
        deliver_alert_notification_channel(delivery.pk)

    delivery.refresh_from_db()
    assert delivery.status == AlertNotificationDelivery.Status.FAILED
    assert delivery.attempts == 1
    assert delivery.next_retry_at is None
    assert delivery.last_error == "receiver does not exist"


@pytest.mark.django_db(transaction=True)
def test_expired_worker_result_cannot_overwrite_new_channel_claim():
    record = AlertOutbox.objects.create(
        kind="notification",
        payload={"params": _params()[:1]},
        idempotency_key="notification:phase2:fencing",
    )
    with mock.patch("apps.alerts.tasks.tasks.deliver_alert_notification_channel.delay"):
        assert deliver_outbox_record(record.pk) is True
    delivery = record.notification_deliveries.get()

    def stale_worker_result(_params):
        AlertNotificationDelivery.objects.filter(pk=delivery.pk).update(updated_at=timezone.now() - timedelta(minutes=10))
        assert (
            deliver_alert_notification_channel.run(
                delivery.pk,
            )
            is True
        )
        return [{"result": False, "message": "late failure"}]

    with mock.patch(
        "apps.alerts.tasks.tasks.sync_notify",
        side_effect=[[{"result": True}]],
    ):
        from apps.alerts.service.notification_delivery import deliver_notification_channel

        assert (
            deliver_notification_channel(
                delivery.pk,
                notify_func=stale_worker_result,
            )
            is False
        )

    delivery.refresh_from_db()
    assert delivery.status == AlertNotificationDelivery.Status.DELIVERED
    assert delivery.attempts == 2
    assert delivery.last_error == ""


@pytest.mark.django_db(transaction=True)
def test_notification_parent_is_idempotent_after_channel_intents_exist():
    record = AlertOutbox.objects.create(
        kind="notification",
        payload={"params": _params()},
        idempotency_key="notification:phase2:idempotent",
    )
    with mock.patch("apps.alerts.tasks.tasks.deliver_alert_notification_channel.delay"):
        assert deliver_outbox_record(record.pk) is True

    first_keys = list(record.notification_deliveries.order_by("position").values_list("delivery_key", flat=True))
    assert deliver_outbox_record(record.pk) is False
    assert list(record.notification_deliveries.order_by("position").values_list("delivery_key", flat=True)) == first_keys


@pytest.mark.django_db(transaction=True)
def test_legacy_delivered_parent_is_not_reinterpreted_or_replayed():
    record = AlertOutbox.objects.create(
        kind="notification",
        payload={"params": _params()},
        idempotency_key="notification:phase2:legacy-delivered",
        status=AlertOutbox.Status.DELIVERED,
        delivered_at=timezone.now(),
    )

    with mock.patch("apps.alerts.tasks.tasks.deliver_alert_notification_channel.delay") as delay:
        assert deliver_outbox_record(record.pk) is False

    assert not record.notification_deliveries.exists()
    delay.assert_not_called()


@pytest.mark.django_db
def test_channel_dispatcher_schedules_pending_and_expired_leases_only():
    record = AlertOutbox.objects.create(
        kind="notification",
        payload={"params": _params()},
        idempotency_key="notification:phase2:dispatch",
        status=AlertOutbox.Status.DELIVERED,
    )
    now = timezone.now()
    pending = AlertNotificationDelivery.objects.create(
        outbox=record,
        position=0,
        delivery_key="pending-key",
        parameter=_params()[0],
        channel_id="11",
        channel_type="email",
    )
    due_retry = AlertNotificationDelivery.objects.create(
        outbox=record,
        position=1,
        delivery_key="retry-key",
        parameter=_params()[1],
        channel_id="22",
        channel_type="sms",
        next_retry_at=now - timedelta(seconds=1),
    )
    stale = AlertNotificationDelivery.objects.create(
        outbox=record,
        position=2,
        delivery_key="stale-key",
        parameter={**_params()[1], "channel_id": 33},
        channel_id="33",
        channel_type="sms",
        status=AlertNotificationDelivery.Status.DELIVERING,
        attempts=1,
        claim_token="stale",
    )
    AlertNotificationDelivery.objects.filter(pk=stale.pk).update(updated_at=now - timedelta(minutes=10))
    future = AlertNotificationDelivery.objects.create(
        outbox=record,
        position=3,
        delivery_key="future-key",
        parameter={**_params()[1], "channel_id": 44},
        channel_id="44",
        channel_type="sms",
        next_retry_at=now + timedelta(minutes=10),
    )
    delivered = AlertNotificationDelivery.objects.create(
        outbox=record,
        position=4,
        delivery_key="delivered-key",
        parameter={**_params()[1], "channel_id": 55},
        channel_id="55",
        channel_type="sms",
        status=AlertNotificationDelivery.Status.DELIVERED,
    )

    with mock.patch("apps.alerts.tasks.tasks.deliver_alert_notification_channel.delay") as delay:
        result = dispatch_pending_alert_notification_deliveries()

    scheduled = {call.args[0] for call in delay.call_args_list}
    assert result == {"scheduled": 3}
    assert scheduled == {pending.pk, due_retry.pk, stale.pk}
    assert future.pk not in scheduled
    assert delivered.pk not in scheduled


@pytest.mark.django_db(transaction=True)
def test_channel_broker_failure_keeps_durable_intent_pending():
    record = AlertOutbox.objects.create(
        kind="notification",
        payload={"params": _params()[:1]},
        idempotency_key="notification:phase2:broker",
    )
    with mock.patch(
        "apps.alerts.tasks.tasks.deliver_alert_notification_channel.delay",
        side_effect=RuntimeError("broker down"),
    ):
        assert deliver_outbox_record(record.pk) is True

    record.refresh_from_db()
    delivery = record.notification_deliveries.get()
    assert record.status == AlertOutbox.Status.DELIVERED
    assert delivery.status == AlertNotificationDelivery.Status.PENDING
    assert delivery.attempts == 0
