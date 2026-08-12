"""Issue #3341：告警中心生命周期投递的真实 ORM/协议回归。"""

from datetime import datetime, timedelta, timezone
from threading import Event, Thread
from types import SimpleNamespace

import pytest
from django.db import close_old_connections
from django.utils import timezone as django_timezone

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
    assert "lifecycle_action" not in delivery.payload
    assert "lifecycle_generation" in delivery.payload
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


def test_multi_channel_enqueue_is_idempotent_across_retries(alert_center_channel, monkeypatch):
    second_channel = Channel.objects.create(
        name="备用告警中心",
        channel_type="nats",
        config={"method_name": "receive_alert_events"},
        description="",
        team=[1],
    )
    monkeypatch.setattr("apps.monitor.services.alert_center_delivery._schedule_deliveries", lambda ids: None)
    alert = _alert(
        alert_center_channel,
        notice_type_ids=[alert_center_channel.id, second_channel.id],
    )
    notifier = AlertLifecycleNotifier(
        SimpleNamespace(id=7, name="CPU 策略", organizations=[1], notice=True)
    )

    first_ids = enqueue_alert_center_deliveries(
        [alert], "created", notifier=notifier
    )
    second_ids = enqueue_alert_center_deliveries(
        [alert], "created", notifier=notifier
    )

    assert len(first_ids) == 2
    assert second_ids == []
    assert MonitorAlertCenterDelivery.objects.filter(alert=alert).count() == 2


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


def test_stale_delivering_lease_is_reclaimed(alert_center_channel, monkeypatch):
    alert = _alert(alert_center_channel, alert_center_notified=False)
    delivery = MonitorAlertCenterDelivery.objects.create(
        alert=alert,
        action="created",
        generation=1,
        delivery_id="stale-lease",
        channel_id=alert_center_channel.id,
        payload={"title": "first", "organizations": [1]},
        status=MonitorAlertCenterDelivery.Status.DELIVERING,
        attempts=1,
    )
    stale_at = django_timezone.now() - timedelta(minutes=6)
    MonitorAlertCenterDelivery.objects.filter(id=delivery.id).update(
        updated_at=stale_at
    )
    monkeypatch.setattr(
        "apps.monitor.services.alert_center_delivery.SystemMgmtUtils.dispatch_notification",
        lambda **kwargs: {"result": True, "data": {}},
    )

    assert deliver_alert_center_delivery(delivery.id) is True

    delivery.refresh_from_db()
    assert delivery.status == MonitorAlertCenterDelivery.Status.DELIVERED
    assert delivery.attempts == 2


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ({"result": False, "data": {"event_results": [{"delivery_id": "d", "status": "duplicate", "retryable": False}]}}, (True, False, "")),
        ({"result": False, "data": {"event_results": [{"delivery_id": "d", "status": "rejected", "retryable": True}]}}, (False, True, "rejected")),
        ({"result": False, "data": {"event_results": [{"delivery_id": "d", "status": "errored", "retryable": True}]}}, (False, True, "errored")),
        ({"result": True, "data": {}}, (True, False, "")),
    ],
)
def test_ack_contract_supports_new_and_legacy_receivers(response, expected):
    assert _ack_result(response, "d") == expected


def test_new_alert_stays_unreconciled_until_outbox_intent_is_persisted(alert_center_channel):
    alert = _alert(alert_center_channel)
    assert alert.alert_center_delivery_backfilled is False


def test_backfill_marks_no_target_rows_reconciled_without_outbox(alert_center_channel):
    alert = _alert(alert_center_channel, policy_id=0, notice_type_ids=[])
    assert backfill_legacy_alerts() == 1
    alert.refresh_from_db()
    assert alert.alert_center_delivery_backfilled is True
    assert not MonitorAlertCenterDelivery.objects.filter(alert=alert).exists()


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


def test_rejected_event_ack_keeps_delivery_retryable(alert_center_channel, monkeypatch):
    alert = _alert(alert_center_channel, alert_center_notified=False)
    delivery = MonitorAlertCenterDelivery.objects.create(
        alert=alert,
        action="created",
        generation=1,
        delivery_id="retryable-rejected",
        channel_id=alert_center_channel.id,
        payload={"title": "first", "organizations": [1]},
    )
    monkeypatch.setattr(
        "apps.monitor.services.alert_center_delivery.SystemMgmtUtils.dispatch_notification",
        lambda **kwargs: {
            "result": False,
            "data": {
                "event_results": [
                    {
                        "delivery_id": "retryable-rejected",
                        "status": "rejected",
                        "retryable": True,
                    }
                ]
            },
        },
    )

    assert deliver_alert_center_delivery(delivery.id) is False

    delivery.refresh_from_db()
    assert delivery.status == MonitorAlertCenterDelivery.Status.PENDING
    assert delivery.attempts == 1
    assert delivery.next_retry_at is not None
    assert delivery.last_error == "rejected"


def test_terminal_predecessor_closes_later_generations(alert_center_channel, monkeypatch):
    alert = _alert(alert_center_channel, alert_center_notified=False)
    first = MonitorAlertCenterDelivery.objects.create(
        alert=alert,
        action="created",
        generation=1,
        delivery_id="terminal-created",
        channel_id=alert_center_channel.id,
        payload={"title": "first", "organizations": [1]},
    )
    second = MonitorAlertCenterDelivery.objects.create(
        alert=alert,
        action="recovered",
        generation=2,
        delivery_id="blocked-recovered",
        channel_id=alert_center_channel.id,
        payload={"title": "second", "organizations": [1]},
    )
    monkeypatch.setattr(
        "apps.monitor.services.alert_center_delivery.SystemMgmtUtils.dispatch_notification",
        lambda **kwargs: {"result": False, "retryable": False, "code": "rejected"},
    )

    assert deliver_alert_center_delivery(first.id) is False

    first.refresh_from_db()
    second.refresh_from_db()
    assert first.status == MonitorAlertCenterDelivery.Status.FAILED
    assert second.status == MonitorAlertCenterDelivery.Status.FAILED
    assert second.last_error == "blocked by terminal generation 1"


def test_successor_enqueued_after_terminal_failure_is_closed(
    alert_center_channel, monkeypatch
):
    alert = _alert(alert_center_channel, alert_center_notified=False)
    first = MonitorAlertCenterDelivery.objects.create(
        alert=alert,
        action="created",
        generation=1,
        delivery_id="terminal-lock-created",
        channel_id=alert_center_channel.id,
        payload={"title": "first", "organizations": [1]},
    )
    monkeypatch.setattr(
        "apps.monitor.services.alert_center_delivery.SystemMgmtUtils.dispatch_notification",
        lambda **kwargs: {"result": False, "retryable": False, "code": "forbidden"},
    )
    monkeypatch.setattr(
        "apps.monitor.services.alert_center_delivery._schedule_deliveries",
        lambda ids: None,
    )

    assert deliver_alert_center_delivery(first.id) is False
    notifier = AlertLifecycleNotifier(
        SimpleNamespace(id=7, name="CPU 策略", organizations=[1], notice=True)
    )
    enqueue_alert_center_deliveries(
        [alert], "recovered", notifier=notifier
    )

    second = MonitorAlertCenterDelivery.objects.get(
        alert=alert, generation=2
    )
    assert second.status == MonitorAlertCenterDelivery.Status.FAILED
    assert second.last_error == "blocked by terminal generation 1"


def test_terminal_finalize_serializes_with_concurrent_successor_enqueue(
    alert_center_channel, monkeypatch
):
    alert = _alert(alert_center_channel, alert_center_notified=False)
    first = MonitorAlertCenterDelivery.objects.create(
        alert=alert,
        action="created",
        generation=1,
        delivery_id="terminal-race-created",
        channel_id=alert_center_channel.id,
        payload={"title": "first", "organizations": [1]},
    )
    notifier = AlertLifecycleNotifier(
        SimpleNamespace(id=7, name="CPU 策略", organizations=[1], notice=True)
    )
    finalize_started = Event()
    allow_finalize = Event()
    enqueue_started = Event()
    enqueue_finished = Event()
    errors = []
    original_fail_successors = (
        __import__(
            "apps.monitor.services.alert_center_delivery",
            fromlist=["_fail_blocked_successors"],
        )._fail_blocked_successors
    )

    def hold_terminal_transaction(record):
        original_fail_successors(record)
        finalize_started.set()
        assert allow_finalize.wait(timeout=5)

    monkeypatch.setattr(
        "apps.monitor.services.alert_center_delivery._fail_blocked_successors",
        hold_terminal_transaction,
    )
    monkeypatch.setattr(
        "apps.monitor.services.alert_center_delivery.SystemMgmtUtils.dispatch_notification",
        lambda **kwargs: {"result": False, "retryable": False, "code": "forbidden"},
    )
    monkeypatch.setattr(
        "apps.monitor.services.alert_center_delivery._schedule_deliveries",
        lambda ids: None,
    )

    def finalize():
        close_old_connections()
        try:
            deliver_alert_center_delivery(first.id)
        except Exception as exc:  # pragma: no cover - assertion reports below
            errors.append(exc)
        finally:
            close_old_connections()

    def enqueue():
        close_old_connections()
        enqueue_started.set()
        try:
            fresh_alert = MonitorAlert.objects.get(id=alert.id)
            enqueue_alert_center_deliveries(
                [fresh_alert], "recovered", notifier=notifier
            )
        except Exception as exc:  # pragma: no cover - assertion reports below
            errors.append(exc)
        finally:
            enqueue_finished.set()
            close_old_connections()

    finalize_thread = Thread(target=finalize)
    enqueue_thread = Thread(target=enqueue)
    finalize_thread.start()
    assert finalize_started.wait(timeout=5)
    enqueue_thread.start()
    assert enqueue_started.wait(timeout=5)
    assert enqueue_finished.wait(timeout=0.2) is False
    allow_finalize.set()
    finalize_thread.join(timeout=5)
    enqueue_thread.join(timeout=5)

    assert errors == []
    assert finalize_thread.is_alive() is False
    assert enqueue_thread.is_alive() is False
    second = MonitorAlertCenterDelivery.objects.get(alert=alert, generation=2)
    assert second.status == MonitorAlertCenterDelivery.Status.FAILED
    assert second.last_error == "blocked by terminal generation 1"
