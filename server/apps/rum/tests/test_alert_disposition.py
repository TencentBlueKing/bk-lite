from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from apps.rum.services.alert_runtime import RumAlertRuntime
from apps.rum.services.alert_store import MemoryEventStore, MemoryPolicyStore
from apps.rum.services.applications import ApplicationsService
from apps.rum.services.control import ControlError, MemoryControl
from apps.rum.services.monitors import MonitorsService
from apps.rum.services.settings import RumRuntimeSettings

pytestmark = pytest.mark.django_db


def _user(user_id, *, disabled=False, orgs=(10,)):
    return SimpleNamespace(id=user_id, username=f"user-{user_id}", disabled=disabled, group_list=[{"id": org} for org in orgs])


def _users(raw):
    directory = {
        11: _user(11),
        12: _user(12, disabled=True),
        13: _user(13, orgs=(99,)),
        14: _user(14),
    }
    try:
        return directory.get(int(raw))
    except (TypeError, ValueError):
        return None


_apps = 0


def _service():
    global _apps
    _apps += 1
    application = f"checkout-{_apps}"
    control = MemoryControl()
    settings = RumRuntimeSettings(
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
    ApplicationsService(control, settings).create_application(
        "tester",
        {"application": application, "origins": ["https://shop.example.test"]},
    )
    policies = MemoryPolicyStore()
    events = MemoryEventStore()
    service = MonitorsService(control=control, policies=policies, events=events, users=_users)
    service.application = application
    return service, policies, events


def _open(service, policies, events, **overrides):
    body = {
        "name": "Checkout errors",
        "application": service.application,
        "organizations": [10],
        "metric": "error_rate",
        "comparator": ">=",
        "warnThreshold": 0.05,
        "criticalThreshold": 0.1,
        "severity": "warning",
        "forDurationSec": 0,
        "noDataAfter": 0,
        "handlers": [],
        "notificationTargets": [],
    }
    body.update(overrides)
    created = service.create_monitor("tester", body, assignable_orgs={10})
    runtime = RumAlertRuntime(policies=policies, alerts=events, analytics=_Value(0.5), tenant_id="core")
    runtime.evaluate_policy(created["id"], datetime(2026, 10, 16, 8, 0, tzinfo=timezone.utc))
    return created, events.active_for_policy(created["id"])


class _Value:
    def __init__(self, value=0.5):
        self.value = value

    def available(self):
        return True

    def monitor_metric(self, tenant_id, opts):
        return self.value

    def metric_series(self, tenant_id, opts):
        return []


def _channel(channel_id, mode="message", recipient_mode="system_user"):
    return {
        "channelId": channel_id,
        "channelName": f"channel-{channel_id}",
        "channelType": "email" if mode == "message" else "nats",
        "deliveryMode": mode,
        "recipientMode": "none" if mode == "alert_event_copy" else recipient_mode,
        "recipients": [] if mode == "alert_event_copy" else ["ops@example.test"],
    }


def test_new_alert_snapshots_handlers_and_policy_edits_do_not_rewrite_it():
    service, policies, events = _service()
    created, alert = _open(service, policies, events, handlers=[11])
    assert alert["handlers"] == [11]
    service.update_monitor(
        "tester",
        created["id"],
        {"handlers": [14]},
        assignable_orgs={10},
        visible_orgs={10},
    )
    assert events.get_alert(alert["id"])["handlers"] == [11]


def test_empty_handlers_can_claim_assign_and_close_but_a_second_claim_conflicts():
    service, policies, events = _service()
    _created, alert = _open(service, policies, events)
    claimed = service.claim_alert(alert["id"], _user(11), visible_orgs={10})
    assert claimed["handlers"] == [11]
    with pytest.raises(ControlError) as conflict:
        service.claim_alert(alert["id"], _user(14), visible_orgs={10})
    assert conflict.value.code == "conflict"
    assert [item["action"] for item in events.list_events(alert["id"])].count("claimed") == 1

    service, policies, events = _service()
    _created, alert = _open(service, policies, events)
    assigned = service.assign_alert(alert["id"], _user(11), [14], visible_orgs={10})
    assert assigned["handlers"] == [14]
    service, policies, events = _service()
    _created, alert = _open(service, policies, events)
    closed = service.close_alert(alert["id"], _user(11), visible_orgs={10})
    assert closed["status"] == "closed"


def test_assign_rejects_disabled_or_out_of_org_users_and_reassign_replaces_the_list():
    service, policies, events = _service()
    _created, alert = _open(service, policies, events)
    with pytest.raises(ControlError) as disabled:
        service.assign_alert(alert["id"], _user(11), [12], visible_orgs={10})
    assert disabled.value.code == "invalid_argument"
    with pytest.raises(ControlError) as outsider:
        service.assign_alert(alert["id"], _user(11), [13], visible_orgs={10})
    assert outsider.value.code == "invalid_argument"
    assert events.get_alert(alert["id"])["handlers"] == []

    assigned = service.assign_alert(alert["id"], _user(11), [11], visible_orgs={10})
    assert assigned["handlers"] == [11]
    with pytest.raises(ControlError) as empty:
        service.reassign_alert(alert["id"], _user(11), [], visible_orgs={10})
    assert empty.value.code == "invalid_argument"
    replaced = service.reassign_alert(alert["id"], _user(11), [14], visible_orgs={10})
    assert replaced["handlers"] == [14]
    with pytest.raises(ControlError) as stranger:
        service.reassign_alert(alert["id"], _user(11), [11], visible_orgs={10})
    assert stranger.value.code == "conflict"
    assert events.get_alert(alert["id"])["handlers"] == [14]


def test_only_the_current_handler_can_close_and_terminal_alerts_stay_closed():
    service, policies, events = _service()
    _created, alert = _open(service, policies, events, handlers=[11])
    with pytest.raises(ControlError) as rejected:
        service.close_alert(alert["id"], _user(14), visible_orgs={10})
    assert rejected.value.code == "conflict"
    assert events.get_alert(alert["id"])["status"] == "active"
    assert service.close_alert(alert["id"], _user(11), visible_orgs={10})["status"] == "closed"
    with pytest.raises(ControlError):
        service.close_alert(alert["id"], _user(11), visible_orgs={10})

    service, policies, events = _service()
    created, alert = _open(service, policies, events)
    RumAlertRuntime(policies=policies, alerts=events, analytics=_Value(0.0), tenant_id="core").evaluate_policy(
        created["id"],
        datetime(2026, 10, 16, 8, 1, tzinfo=timezone.utc),
    )
    assert events.get_alert(alert["id"])["status"] == "recovered"
    with pytest.raises(ControlError):
        service.close_alert(alert["id"], _user(11), visible_orgs={10})
    assert events.get_alert(alert["id"])["status"] == "recovered"


def test_my_alerts_filter_keeps_only_visible_alerts_for_the_current_handler():
    service, policies, events = _service()
    _open(service, policies, events, name="mine", handlers=[11])
    _open(service, policies, events, name="theirs", handlers=[14])
    mine = service.list_alert_events({"handler": "11", "status": "active"}, visible_orgs={10})
    assert mine["total"] == 1
    assert mine["items"][0]["policyName"] == "mine"
    hidden = service.list_alert_events({"handler": "11"}, visible_orgs=set())
    assert hidden["items"] == []


def test_assign_and_reassign_notify_person_channels_only():
    service, policies, events = _service()
    _created, alert = _open(
        service,
        policies,
        events,
        notificationTargets=[
            _channel(4, recipient_mode="system_user"),
            _channel(5, recipient_mode="free_text"),
            _channel(9, mode="alert_event_copy"),
            _channel(8, recipient_mode="none"),
        ],
    )
    before = len(events.list_deliveries(alert["id"]))
    service.claim_alert(alert["id"], _user(11), visible_orgs={10})
    assert len(events.list_deliveries(alert["id"])) == before
    service, policies, events = _service()
    _created, alert = _open(
        service,
        policies,
        events,
        notificationTargets=[_channel(4), _channel(9, mode="alert_event_copy")],
    )
    opened = [item for item in events.list_deliveries(alert["id"]) if item["deliveryMode"] == "alert_event_copy"]
    assert opened
    service.assign_alert(alert["id"], _user(11), [14], visible_orgs={10})
    added = [item for item in events.list_deliveries(alert["id"]) if ":assigned:" in item["deliveryKey"]]
    assert len(added) == 1
    assert added[0]["deliveryMode"] == "message"
    assert added[0]["recipients"] == ["14"]
    service.reassign_alert(alert["id"], _user(14), [11], visible_orgs={10})
    reassigned = [item for item in events.list_deliveries(alert["id"]) if ":reassigned:" in item["deliveryKey"]]
    assert len(reassigned) == 1
    assert reassigned[0]["recipients"] == ["11"]


def test_manual_retry_accepts_only_terminal_failures_and_writes_an_audit():
    service, policies, events = _service()
    _created, alert = _open(service, policies, events, notificationTargets=[_channel(4, recipient_mode="free_text")])
    delivery = events.list_deliveries(alert["id"])[0]
    with pytest.raises(ControlError) as pending:
        service.retry_alert_delivery(alert["id"], delivery["id"], _user(11), visible_orgs={10})
    assert pending.value.code == "conflict"
    delivery["status"] = "failed"
    delivery["attempts"] = 3
    delivery["lastErrorCode"] = "channel_not_found"
    delivery["lastErrorMessage"] = "通知渠道不存在。"
    events.save_delivery(delivery)
    retried = service.retry_alert_delivery(alert["id"], delivery["id"], _user(11), visible_orgs={10})
    assert retried["status"] == "pending"
    assert retried["attempts"] == 0
    audit = events.list_retries(delivery["id"])
    assert audit[0]["previousAttempts"] == 3
    assert audit[0]["previousErrorCode"] == "channel_not_found"
    assert audit[0]["requestedBy"] == "user-11"
