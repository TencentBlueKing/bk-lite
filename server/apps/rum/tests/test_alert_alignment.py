from datetime import datetime, timedelta, timezone

import pytest

from apps.rum.services.alert_runtime import RumAlertRuntime
from apps.rum.services.alert_store import DjangoEventStore, DjangoPolicyStore, MemoryEventStore, MemoryPolicyStore
from apps.rum.services.applications import ApplicationsService
from apps.rum.services.control import ControlError, MemoryControl
from apps.rum.services.delivery import SystemMgmtAlertDispatcher
from apps.rum.services.monitors import MonitorsService
from apps.rum.services.settings import RumRuntimeSettings
from apps.rum.services.validation import ValidationError
from apps.rum.services.victoria_analytics import VictoriaAnalytics

pytestmark = pytest.mark.django_db


def _settings() -> RumRuntimeSettings:
    return RumRuntimeSettings(
        collect_url="https://telemetry.example.test/rum/v1/collect",
        replay_url="https://telemetry.example.test/rum/v1/replay",
        sdk_cdn_url="https://cdn.example.test/rum/bklite-rum-sdk.js",
        nats_url="",
        nats_timeout_seconds=5,
        tenant_id="core",
        victoria_logs_url="",
        victoria_traces_url="",
        victoria_account_id=0,
        victoria_project_id=0,
        victoria_timeout_seconds=15,
    )


def _service():
    control = MemoryControl()
    ApplicationsService(control, _settings()).create_application(
        "tester",
        {"application": "checkout", "origins": ["https://shop.example.test"]},
    )
    ApplicationsService(control, _settings()).create_application(
        "tester",
        {"application": "catalog", "origins": ["https://catalog.example.test"]},
    )
    policies = MemoryPolicyStore()
    events = MemoryEventStore()
    return MonitorsService(control=control, policies=policies, events=events), policies, events


def _body(**overrides):
    body = {
        "name": "Checkout errors",
        "application": "checkout",
        "organizations": [10],
        "metric": "error_rate",
        "comparator": ">=",
        "warnThreshold": 0.05,
        "criticalThreshold": 0.1,
        "severity": "warning",
        "forDurationSec": 0,
        "noDataAfter": 0,
        "evaluationWindowMinutes": 15,
        "notificationTargets": [],
    }
    body.update(overrides)
    return body


def _channel(channel_id, *, mode="message", recipient_mode="system_user", recipients=None):
    return {
        "channelId": channel_id,
        "channelName": f"channel-{channel_id}",
        "channelType": "email" if mode == "message" else "nats",
        "deliveryMode": mode,
        "recipientMode": "none" if mode == "alert_event_copy" else recipient_mode,
        "recipients": [] if mode == "alert_event_copy" else list(recipients or ["11"]),
    }


class ScriptedAnalytics:
    def __init__(self, values):
        self.values = list(values)
        self.calls = 0

    def available(self):
        return True

    def monitor_metric(self, tenant_id, opts):
        value = self.values[min(self.calls, len(self.values) - 1)]
        self.calls += 1
        if isinstance(value, Exception):
            raise value
        return value

    def metric_series(self, tenant_id, opts):
        return []


class RecordingDispatcher:
    def __init__(self, results):
        self.results = list(results)
        self.sent = []
        self.calls = 0

    def dispatch(self, delivery):
        self.calls += 1
        result = self.results[min(self.calls - 1, len(self.results) - 1)]
        if isinstance(result, Exception):
            raise result
        if result.get("delivered"):
            self.sent.append(delivery["deliveryKey"])
        return result


def _runtime(policies, events, values, dispatcher=None):
    return RumAlertRuntime(
        policies=policies,
        alerts=events,
        analytics=ScriptedAnalytics(values),
        dispatcher=dispatcher,
        tenant_id="core",
    )


def test_create_policy_requires_organization_and_hides_other_orgs():
    service, _policies, _events = _service()
    with pytest.raises(ValidationError):
        service.create_monitor("tester", _body(organizations=[]), assignable_orgs={10})
    with pytest.raises(ControlError) as forbidden:
        service.create_monitor("tester", _body(organizations=[99]), assignable_orgs={10})
    assert forbidden.value.code == "forbidden"

    created = service.create_monitor("tester", _body(), assignable_orgs={10})
    assert service.list_monitors(visible_orgs={10})[0]["id"] == created["id"]
    assert service.list_monitors(visible_orgs={20}) == []
    with pytest.raises(ControlError) as missing:
        service.update_monitor("tester", created["id"], {"name": "hidden"}, assignable_orgs={10}, visible_orgs={20})
    assert missing.value.code == "not_found"


def test_same_minute_opens_one_alert_and_recovery_writes_both_events():
    service, policies, events = _service()
    created = service.create_monitor("tester", _body(), assignable_orgs={10})
    start = datetime(2026, 10, 16, 8, 0, tzinfo=timezone.utc)
    runtime = _runtime(policies, events, [0.5, 0.01])
    assert runtime.evaluate_policy(created["id"], start) == "fired"
    assert runtime.evaluate_policy(created["id"], start) == "duplicate"
    alert = events.active_for_policy(created["id"])
    assert alert["status"] == "active"
    assert runtime.evaluate_policy(created["id"], start + timedelta(minutes=1)) == "recovered"
    saved = events.get_alert(alert["id"])
    assert saved["status"] == "recovered"
    assert [item["action"] for item in events.list_events(alert["id"])] == ["triggered", "recovered"]
    assert events.active_for_policy(created["id"]) is None


def test_missing_rows_do_not_trip_a_less_than_policy_until_a_real_zero():
    service, policies, events = _service()
    created = service.create_monitor(
        "tester",
        _body(metric="session_count", comparator="<", warnThreshold=0, criticalThreshold=1, noDataAfter=0),
        assignable_orgs={10},
    )
    start = datetime(2026, 10, 16, 8, 0, tzinfo=timezone.utc)
    runtime = _runtime(policies, events, [None, None, 0.0])
    assert runtime.evaluate_policy(created["id"], start) == "none"
    assert runtime.evaluate_policy(created["id"], start + timedelta(minutes=1)) == "none"
    assert events.active_for_policy(created["id"]) is None
    assert runtime.evaluate_policy(created["id"], start + timedelta(minutes=2)) == "fired"
    assert events.active_for_policy(created["id"])["currentValue"] == 0.0


def test_no_data_streak_fires_and_a_later_value_recovers():
    service, policies, events = _service()
    created = service.create_monitor("tester", _body(noDataAfter=3, severity="critical"), assignable_orgs={10})
    start = datetime(2026, 10, 16, 8, 0, tzinfo=timezone.utc)
    runtime = _runtime(policies, events, [None, None, None, 0.01])
    assert runtime.evaluate_policy(created["id"], start) == "none"
    assert runtime.evaluate_policy(created["id"], start + timedelta(minutes=1)) == "none"
    assert runtime.evaluate_policy(created["id"], start + timedelta(minutes=2)) == "fired"
    alert = events.active_for_policy(created["id"])
    assert alert["currentValue"] is None
    assert alert["severity"] == "critical"
    assert runtime.evaluate_policy(created["id"], start + timedelta(minutes=3)) == "recovered"
    assert events.get_alert(alert["id"])["status"] == "recovered"


def test_metric_read_failure_skips_only_that_policy():
    service, policies, events = _service()
    broken = service.create_monitor("tester", _body(name="broken"), assignable_orgs={10})
    healthy = service.create_monitor(
        "tester",
        _body(name="healthy", application="catalog"),
        assignable_orgs={10},
    )

    class Selective:
        def available(self):
            return True

        def monitor_metric(self, tenant_id, opts):
            if opts["application"] == "checkout":
                raise TimeoutError("victoria-down")
            return 0.5

        def metric_series(self, tenant_id, opts):
            return []

    start = datetime(2026, 10, 16, 8, 0, tzinfo=timezone.utc)
    runtime = RumAlertRuntime(policies=policies, alerts=events, analytics=Selective(), tenant_id="core")
    assert runtime.evaluate_policy(broken["id"], start) == "failed"
    assert runtime.evaluate_policy(healthy["id"], start) == "fired"
    assert policies.get(broken["id"])["lastEvaluationResult"] == "failed"
    assert policies.get(broken["id"])["lastFailedAt"]
    assert events.active_for_policy(healthy["id"])["status"] == "active"
    assert events.active_for_policy(broken["id"]) is None


def test_disable_closes_active_alert_and_delete_keeps_snapshot():
    service, policies, events = _service()
    created = service.create_monitor("tester", _body(name="Checkout errors"), assignable_orgs={10})
    start = datetime(2026, 10, 16, 8, 0, tzinfo=timezone.utc)
    _runtime(policies, events, [0.5]).evaluate_policy(created["id"], start)
    alert_id = events.active_for_policy(created["id"])["id"]
    service.update_monitor(
        "tester",
        created["id"],
        {**_body(), "enabled": False},
        assignable_orgs={10},
        visible_orgs={10},
    )
    closed = events.get_alert(alert_id)
    assert closed["status"] == "closed"
    assert closed["operator"] == "system"
    assert events.list_events(alert_id)[-1]["content"]["actor"] == "system"

    again = service.create_monitor("tester", _body(name="Kept name"), assignable_orgs={10})
    _runtime(policies, events, [0.5]).evaluate_policy(again["id"], start + timedelta(minutes=1))
    kept_id = events.active_for_policy(again["id"])["id"]
    service.delete_monitor(again["id"], visible_orgs={10})
    kept = events.get_alert(kept_id)
    assert kept["status"] == "closed"
    assert kept["policyName"] == "Kept name"
    assert kept["application"] == "checkout"
    assert kept["metric"] == "error_rate"
    assert policies.get(again["id"]) is None


def test_delivery_retries_once_then_succeeds_without_a_second_send():
    service, policies, events = _service()
    created = service.create_monitor(
        "tester",
        _body(notificationTargets=[_channel(4, recipient_mode="free_text", recipients=["ops@example.test"])]),
        assignable_orgs={10},
    )
    start = datetime(2026, 10, 16, 8, 0, tzinfo=timezone.utc)
    dispatcher = RecordingDispatcher(
        [
            {"delivered": False, "retryable": True, "code": "timeout", "message": "later"},
            {"delivered": True, "retryable": False, "code": "delivered", "message": "ok"},
        ]
    )
    runtime = _runtime(policies, events, [0.5], dispatcher=dispatcher)
    runtime.evaluate_policy(created["id"], start)
    assert runtime.deliver_due(start)["failed"] == 1
    assert dispatcher.sent == []
    assert runtime.deliver_due(start)["sent"] == 0
    assert runtime.deliver_due(start + timedelta(seconds=5))["sent"] == 1
    assert dispatcher.sent == dispatcher.sent[:1]
    alert_id = next(iter(events.alerts))
    saved = events.list_deliveries(alert_id)[0]
    assert saved["status"] == "delivered"
    assert saved["attempts"] == 2
    assert runtime.deliver_due(start + timedelta(minutes=1))["sent"] == 0
    assert len(dispatcher.sent) == 1


@pytest.mark.parametrize(
    ("code", "message"),
    [
        ("channel_not_found", "通知渠道不存在。"),
        ("invalid_recipients", "通知接收人不符合渠道能力。"),
        ("channel_forbidden", "通知渠道不属于事件组织范围。"),
    ],
)
def test_terminal_delivery_failure_keeps_the_reason(code, message):
    service, policies, events = _service()
    created = service.create_monitor(
        "tester",
        _body(notificationTargets=[_channel(5, recipient_mode="free_text", recipients=["ops@example.test"])]),
        assignable_orgs={10},
    )
    start = datetime(2026, 10, 16, 8, 0, tzinfo=timezone.utc)
    dispatcher = RecordingDispatcher([{"delivered": False, "retryable": True, "code": code, "message": message}])
    runtime = _runtime(policies, events, [0.5], dispatcher=dispatcher)
    runtime.evaluate_policy(created["id"], start)
    assert runtime.deliver_due(start)["failed"] == 1
    delivery = events.list_deliveries(next(iter(events.alerts)))[0]
    assert delivery["status"] == "failed"
    assert delivery["lastErrorCode"] == code
    assert delivery["lastErrorMessage"] == message
    assert runtime.deliver_due(start + timedelta(minutes=10))["sent"] == 0
    assert dispatcher.calls == 1


def test_renotify_waits_for_the_interval_and_skips_the_alert_center_copy():
    service, policies, events = _service()
    created = service.create_monitor(
        "tester",
        _body(
            renotifyMinutes=5,
            notificationTargets=[
                _channel(4, recipient_mode="free_text", recipients=["ops@example.test"]),
                _channel(9, mode="alert_event_copy"),
            ],
        ),
        assignable_orgs={10},
    )
    start = datetime(2026, 10, 16, 8, 0, tzinfo=timezone.utc)
    runtime = _runtime(policies, events, [0.5])
    runtime.evaluate_policy(created["id"], start)
    alert_id = events.active_for_policy(created["id"])["id"]
    assert len(events.list_events(alert_id)) == 1
    assert {item["deliveryMode"] for item in events.list_deliveries(alert_id)} == {"message", "alert_event_copy"}
    assert runtime.evaluate_policy(created["id"], start + timedelta(minutes=4)) == "none"
    assert len(events.list_deliveries(alert_id)) == 2
    assert runtime.evaluate_policy(created["id"], start + timedelta(minutes=5)) == "renotified"
    deliveries = events.list_deliveries(alert_id)
    assert len(deliveries) == 3
    assert len(events.list_events(alert_id)) == 1
    renotify = [item for item in deliveries if ":renotify:" in item["deliveryKey"]]
    assert len(renotify) == 1
    assert renotify[0]["deliveryMode"] == "message"
    assert renotify[0]["eventId"] is None


def test_alert_center_copy_uses_lite_rum_and_is_omitted_without_that_channel():
    service, policies, events = _service()
    created = service.create_monitor(
        "tester",
        _body(severity="critical", notificationTargets=[_channel(9, mode="alert_event_copy")]),
        assignable_orgs={10},
    )
    start = datetime(2026, 10, 16, 8, 0, tzinfo=timezone.utc)
    _runtime(policies, events, [0.5]).evaluate_policy(created["id"], start)
    delivery = events.list_deliveries(next(iter(events.alerts)))[0]
    assert delivery["payload"]["pusher"] == "lite-rum"
    assert delivery["payload"]["resource_type"] == "rum_application"
    assert delivery["payload"]["resource_id"] == "checkout"
    assert delivery["payload"]["resource_name"] == "checkout"
    assert delivery["payload"]["level"] == "0"
    assert delivery["payload"]["severity"] == "critical"

    plain = service.create_monitor(
        "tester",
        _body(
            name="mail only",
            application="catalog",
            notificationTargets=[_channel(4, recipient_mode="free_text", recipients=["ops@example.test"])],
        ),
        assignable_orgs={10},
    )
    _runtime(policies, events, [0.5]).evaluate_policy(plain["id"], start + timedelta(minutes=1))
    modes = [item["deliveryMode"] for item in events.list_deliveries(events.active_for_policy(plain["id"])["id"])]
    assert modes == ["message"]

    client = _FakeClient()
    result = SystemMgmtAlertDispatcher(client=client).dispatch(delivery)
    assert result["delivered"] is True
    assert client.kwargs["producer"] == "lite-rum"
    assert client.kwargs["internal_caller"] == "lite-rum"
    assert client.kwargs["event_payload"]["resource_type"] == "rum_application"


def test_alert_list_filters_status_application_keyword_and_page():
    service, policies, events = _service()
    checkout = service.create_monitor("tester", _body(name="Checkout errors"), assignable_orgs={10})
    catalog = service.create_monitor(
        "tester",
        _body(name="Catalog latency", application="catalog", metric="lcp_p75", warnThreshold=2000, criticalThreshold=4000),
        assignable_orgs={10},
    )
    start = datetime(2026, 10, 16, 8, 0, tzinfo=timezone.utc)
    _runtime(policies, events, [0.5]).evaluate_policy(checkout["id"], start)
    _runtime(policies, events, [5000, 10]).evaluate_policy(catalog["id"], start)
    _runtime(policies, events, [10]).evaluate_policy(catalog["id"], start + timedelta(minutes=1))

    active = service.list_alert_events({"status": "active", "page": 1, "limit": 15}, visible_orgs={10})
    assert active["total"] == 1
    assert active["items"][0]["application"] == "checkout"
    history = service.list_alert_events({"status": "history", "application": "catalog"}, visible_orgs={10})
    assert history["total"] == 1
    assert history["items"][0]["policyName"] == "Catalog latency"
    keyword = service.list_alert_events({"keyword": "latency"}, visible_orgs={10})
    assert keyword["total"] == 1
    hidden = service.list_alert_events({"status": "active"}, visible_orgs=set())
    assert hidden["items"] == []
    paged = service.list_alert_events({"page": 1, "limit": 1}, visible_orgs={10})
    assert paged["total"] == 2
    assert len(paged["items"]) == 1


def test_dispatcher_exception_keeps_one_traceback_and_hides_the_payload(caplog):
    import traceback

    service, policies, events = _service()
    secret = "rum-delivery-payload-sentinel-77ab"
    created = service.create_monitor(
        "tester",
        _body(notificationTargets=[_channel(4, recipient_mode="free_text", recipients=[secret])]),
        assignable_orgs={10},
    )
    start = datetime(2026, 10, 16, 8, 0, tzinfo=timezone.utc)
    runtime = _runtime(policies, events, [0.5], dispatcher=_Exploding(secret))
    runtime.evaluate_policy(created["id"], start)
    with caplog.at_level("ERROR", logger="rum"):
        result = runtime.deliver_due(start)
    assert result == {"sent": 0, "failed": 1}
    delivery = events.list_deliveries(next(iter(events.alerts)))[0]
    assert delivery["status"] == "pending"
    errors = [record for record in caplog.records if record.levelname == "ERROR"]
    assert len(errors) == 1
    record = errors[0]
    assert record.msg == "rum alert delivery traceback delivery_id=%s failed_stage=%s error_type=%s"
    assert record.args[1:] == ("dispatch", "RuntimeError")
    rendered = record.getMessage()
    formatted = "".join(traceback.format_exception(*record.exc_info)) if record.exc_info else ""
    assert secret not in rendered
    assert secret not in formatted
    assert secret not in caplog.text
    assert record.exc_info[1].__traceback__ is not None


def test_monitor_metric_distinguishes_missing_rows_from_zero():
    analytics = VictoriaAnalytics(client=None)
    analytics._stats = lambda *args, **kwargs: []
    assert analytics.monitor_metric("core", {"application": "checkout", "metric": "session_count"}) is None
    analytics._stats = lambda *args, **kwargs: [{"value": "0", "sessions": "0"}]
    assert analytics.monitor_metric("core", {"application": "checkout", "metric": "session_count"}) == 0.0
    assert analytics.monitor_metric("core", {"application": "checkout", "metric": "error_rate"}) is None


def test_django_store_same_minute_does_not_open_a_second_alert():
    from apps.rum.models import RumAlert

    policies = DjangoPolicyStore()
    events = DjangoEventStore()
    saved = policies.save(_body(notificationTargets=[_channel(4, recipient_mode="free_text", recipients=["ops@example.test"])]))
    start = datetime(2026, 10, 16, 8, 0, tzinfo=timezone.utc)
    runtime = _runtime(policies, events, [0.5, 0.5])
    assert runtime.evaluate_policy(saved["id"], start) == "fired"
    assert runtime.evaluate_policy(saved["id"], start) == "duplicate"
    assert RumAlert.objects.filter(policy_id_snapshot=saved["id"], status="active").count() == 1


@pytest.mark.django_db(transaction=True)
def test_django_store_row_locks_stay_inside_transactions(monkeypatch):
    """sqlite 不校验 select_for_update 的事务边界，Postgres 会直接抛错；这里显式守住每个写路径。"""

    from types import SimpleNamespace

    from django.db import connection
    from django.db.models import QuerySet

    from apps.rum.models import RumAlertDelivery
    from apps.system_mgmt.models import User

    original = QuerySet.select_for_update
    outside: list[str] = []

    def guarded(self, *args, **kwargs):
        if not connection.in_atomic_block:
            outside.append(self.model.__name__)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(QuerySet, "select_for_update", guarded)

    control = MemoryControl()
    ApplicationsService(control, _settings()).create_application(
        "tester",
        {"application": "checkout", "origins": ["https://shop.example.test"]},
    )
    policies = DjangoPolicyStore()
    events = DjangoEventStore()
    db_user = User.objects.create(username="user-11", display_name="值班甲", domain="domain.com")
    user = SimpleNamespace(id=db_user.id, username="user-11", disabled=False, group_list=[{"id": 10}])
    service = MonitorsService(control=control, policies=policies, events=events, users=lambda raw: user)
    created = service.create_monitor(
        "tester",
        _body(notificationTargets=[_channel(4, recipient_mode="free_text", recipients=["ops@example.test"])]),
        assignable_orgs={10},
    )
    start = datetime(2026, 10, 16, 8, 0, tzinfo=timezone.utc)
    dispatcher = RecordingDispatcher([{"delivered": False, "retryable": False, "code": "channel_missing", "message": "渠道不存在"}])
    runtime = _runtime(policies, events, [0.5], dispatcher=dispatcher)
    assert runtime.evaluate_policy(created["id"], start) == "fired"
    assert runtime.deliver_due(start)["failed"] == 1

    alert = events.active_for_policy(created["id"])
    delivery = RumAlertDelivery.objects.get(alert_id=alert["id"])
    assert delivery.status == "failed"
    assert delivery.last_error_code == "channel_missing"

    service.update_monitor("tester", created["id"], {"severity": "critical"}, assignable_orgs={10}, visible_orgs={10})
    service.retry_alert_delivery(alert["id"], str(delivery.id), user, visible_orgs={10})
    assert RumAlertDelivery.objects.get(pk=delivery.id).status == "pending"
    service.claim_alert(alert["id"], user, visible_orgs={10})
    mine = service.list_alert_events({"handler": str(db_user.id), "status": "active"}, visible_orgs={10})
    assert [item["id"] for item in mine["items"]] == [alert["id"]]
    assert mine["items"][0]["handlersDisplay"] == ["值班甲(user-11)"]
    assert service.get_alert_event(alert["id"], visible_orgs={10})["alert"]["handlersDisplay"] == ["值班甲(user-11)"]
    assert service.list_alert_events({"handler": "999999"}, visible_orgs={10})["total"] == 0
    assert service.list_alert_events({}, visible_orgs={20})["total"] == 0
    closed = service.close_alert(alert["id"], user, visible_orgs={10})

    assert closed["status"] == "closed"
    assert outside == []


class _FakeClient:
    def __init__(self):
        self.kwargs = None

    def dispatch_notification(self, **kwargs):
        self.kwargs = kwargs
        return {"result": True, "code": "delivered", "message": "success"}


class _Exploding:
    def __init__(self, secret):
        self.secret = secret

    def dispatch(self, delivery):
        raise RuntimeError(self.secret)
