"""Issue #3341：告警中心生命周期投递的真实 ORM/协议回归。"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from apps.monitor.models import MonitorAlert, MonitorAlertCenterDelivery
from apps.monitor.services.alert_center_delivery import (
    _env_flag,
    _ack_result,
    backfill_legacy_alerts,
    deliver_alert_center_delivery,
    enqueue_alert_center_deliveries,
)
from apps.monitor.tasks import monitor_policy as monitor_policy_tasks
from apps.monitor.services.alert_lifecycle_notify import AlertLifecycleNotifier
from apps.system_mgmt.models import Channel


pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def alert_center_channel():
    return Channel.objects.create(
        name="告警中心",
        channel_type="nats",
        config={"method_name": "receive_alert_events"},
        description="",
        team=[1],
    )


def _alert(channel, **overrides):
    values = {
        "policy_id": 7,
        "monitor_instance_id": "host-1",
        "monitor_instance_name": "主机 1",
        "metric_instance_id": "cpu",
        "content": "CPU 高",
        "level": "warning",
        "value": 80,
        "status": "new",
        "start_event_time": datetime(2026, 8, 12, 1, tzinfo=timezone.utc),
        "notice_type_ids": [channel.id],
        "alert_center_notified": True,
    }
    values.update(overrides)
    return MonitorAlert.objects.create(**values)


def test_outbox_requires_explicit_receiver_first_enablement(monkeypatch):
    monkeypatch.delenv("MONITOR_ALERT_CENTER_OUTBOX_ENABLED", raising=False)
    assert _env_flag("MONITOR_ALERT_CENTER_OUTBOX_ENABLED") is False

    monkeypatch.setenv("MONITOR_ALERT_CENTER_OUTBOX_ENABLED", "true")
    assert _env_flag("MONITOR_ALERT_CENTER_OUTBOX_ENABLED") is True


def test_outbox_rollback_keeps_legacy_created_retry_enabled(monkeypatch):
    assert monitor_policy_tasks._legacy_alert_center_retry_statuses(
        outbox_enabled=False,
        created_retry_enabled=False,
    ) == ["new", "recovered", "closed"]


def test_backfill_reconciles_legacy_created_rows_that_still_look_notified(alert_center_channel, monkeypatch):
    alert = _alert(
        alert_center_channel,
        alert_center_delivery_backfilled=False,
        alert_center_notified=True,
    )
    monkeypatch.setattr("apps.monitor.services.alert_center_delivery._schedule_deliveries", lambda ids: None)

    assert backfill_legacy_alerts() == 1

    delivery = MonitorAlertCenterDelivery.objects.get(alert=alert)
    assert delivery.action == "created"
    assert delivery.channel_id == alert_center_channel.id
    alert.refresh_from_db()
    assert alert.alert_center_delivery_backfilled is True
    assert alert.alert_center_notified is False


def test_created_and_recovered_keep_independent_ordered_immutable_payloads(alert_center_channel, monkeypatch):
    monkeypatch.setattr("apps.monitor.services.alert_center_delivery._schedule_deliveries", lambda ids: None)
    alert = _alert(alert_center_channel)
    notifier = AlertLifecycleNotifier(SimpleNamespace(id=7, name="CPU 策略", organizations=[1], notice=True))

    enqueue_alert_center_deliveries([alert], "created", notifier=notifier)
    created_payload = MonitorAlertCenterDelivery.objects.get(alert=alert, generation=1).payload

    alert.status = "recovered"
    alert.content = "CPU 已恢复"
    alert.end_event_time = datetime(2026, 8, 12, 2, tzinfo=timezone.utc)
    alert.alert_center_notified = False
    alert.save(update_fields=["status", "content", "end_event_time", "alert_center_notified", "updated_at"])
    enqueue_alert_center_deliveries([alert], "recovered", notifier=notifier)

    deliveries = list(MonitorAlertCenterDelivery.objects.filter(alert=alert).order_by("generation"))
    assert [(item.action, item.generation) for item in deliveries] == [("created", 1), ("recovered", 2)]
    assert deliveries[0].payload == created_payload
    assert deliveries[0].payload["title"] == "CPU 高"
    assert deliveries[1].payload["title"] == "CPU 已恢复"
    alert.refresh_from_db()
    assert alert.alert_center_notified is False


def test_later_generation_cannot_overtake_pending_created(alert_center_channel, mocker):
    alert = _alert(alert_center_channel)
    first = MonitorAlertCenterDelivery.objects.create(
        alert=alert, action="created", generation=1, delivery_id="created-1", channel_id=alert_center_channel.id, payload={"title": "first"}
    )
    second = MonitorAlertCenterDelivery.objects.create(
        alert=alert, action="recovered", generation=2, delivery_id="recovered-2", channel_id=alert_center_channel.id, payload={"title": "second"}
    )
    send = mocker.patch("apps.monitor.services.alert_center_delivery.SystemMgmtUtils.dispatch_notification")

    assert deliver_alert_center_delivery(second.id) is False
    send.assert_not_called()
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.status == MonitorAlertCenterDelivery.Status.PENDING
    assert second.status == MonitorAlertCenterDelivery.Status.PENDING


def test_outbox_rollout_keeps_legacy_delivery_and_pending_until_ack(alert_center_channel, mocker, monkeypatch):
    alert = _alert(alert_center_channel, alert_center_notified=False)
    notifier = AlertLifecycleNotifier(SimpleNamespace(id=7, name="CPU 策略", organizations=[1], notice=True))
    monkeypatch.setattr(notifier, "enqueue_alert_center_deliveries", lambda *args, **kwargs: [])
    send = mocker.patch(
        "apps.monitor.services.alert_lifecycle_notify.SystemMgmtUtils.send_msg_with_channel",
        return_value={"result": False, "message": "temporary"},
    )

    notifier.notify_alerts([alert], "created")

    send.assert_called_once()
    alert.refresh_from_db()
    assert alert.alert_center_notified is False


def test_stale_delivery_finalize_is_fenced_by_attempt_generation(alert_center_channel, monkeypatch):
    alert = _alert(alert_center_channel, alert_center_notified=False)
    delivery = MonitorAlertCenterDelivery.objects.create(
        alert=alert, action="created", generation=1, delivery_id="created-fenced", channel_id=alert_center_channel.id, payload={"title": "first"}
    )

    def race(*args, **kwargs):
        MonitorAlertCenterDelivery.objects.filter(id=delivery.id).update(attempts=2)
        return {"result": True, "data": {}}

    monkeypatch.setattr("apps.monitor.services.alert_center_delivery.SystemMgmtUtils.dispatch_notification", race)

    assert deliver_alert_center_delivery(delivery.id) is False
    delivery.refresh_from_db()
    alert.refresh_from_db()
    assert delivery.status == MonitorAlertCenterDelivery.Status.DELIVERING
    assert delivery.attempts == 2
    assert alert.alert_center_notified is False


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ({"result": False, "data": {"event_results": [{"delivery_id": "d", "status": "duplicate", "retryable": False}]}}, (True, False, "")),
        ({"result": False, "data": {"event_results": [{"delivery_id": "d", "status": "rejected", "retryable": False}]}}, (False, False, "rejected")),
        ({"result": False, "data": {"event_results": [{"delivery_id": "d", "status": "errored", "retryable": True}]}}, (False, True, "errored")),
        ({"result": True, "data": {}}, (True, False, "")),
    ],
)
def test_ack_contract_supports_new_and_legacy_receivers(response, expected):
    assert _ack_result(response, "d") == expected


def test_new_alert_stays_unreconciled_until_outbox_intent_is_persisted(alert_center_channel):
    alert = _alert(alert_center_channel)
    assert alert.alert_center_delivery_backfilled is False


def test_terminal_channel_boundary_failure_is_not_retried(alert_center_channel, monkeypatch):
    alert = _alert(alert_center_channel, alert_center_notified=False)
    delivery = MonitorAlertCenterDelivery.objects.create(
        alert=alert,
        action="created",
        generation=1,
        delivery_id="forbidden",
        channel_id=alert_center_channel.id,
        payload={"title": "first", "organizations": [1]},
    )
    monkeypatch.setattr(
        "apps.monitor.services.alert_center_delivery.SystemMgmtUtils.dispatch_notification",
        lambda **kwargs: {
            "result": False,
            "code": "channel_forbidden",
            "retryable": False,
            "message": "forbidden",
        },
    )

    assert deliver_alert_center_delivery(delivery.id) is False
    delivery.refresh_from_db()
    assert delivery.status == MonitorAlertCenterDelivery.Status.FAILED
    assert delivery.next_retry_at is None
