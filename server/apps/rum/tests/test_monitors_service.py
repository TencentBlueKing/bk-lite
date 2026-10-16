from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.django_db

from apps.rum.services.alerteval import breached, should_renotify
from apps.rum.services.analytics import UnavailableAnalytics
from apps.rum.services.applications import ApplicationsService
from apps.rum.services.control import MemoryControl
from apps.rum.services.evaluator import AlertEvaluator
from apps.rum.services.monitors import MemoryEventStore, MemoryPolicyStore, MonitorsService, normalize_alert_policy
from apps.rum.services.notify import MemoryNotifier, render_template
from apps.rum.services.settings import RumRuntimeSettings
from apps.rum.services.validation import ValidationError


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


def _seed_app(control: MemoryControl) -> None:
    ApplicationsService(control, _settings()).create_application(
        "tester",
        {"application": "checkout", "origins": ["https://shop.example.test"]},
    )


class FakeAnalytics:
    def __init__(self, value: float = 0.9):
        self.value = value

    def available(self) -> bool:
        return True

    def monitor_metric(self, tenant_id: str, opts: dict) -> float:
        return self.value

    def metric_series(self, tenant_id: str, opts: dict) -> list[dict]:
        return [{"atMs": 1, "value": self.value}]


def test_normalize_alert_policy_rejects_bad_metric():
    try:
        normalize_alert_policy(
            {
                "name": "High errors",
                "application": "checkout",
                "organizations": [10],
                "metric": "nope",
                "criticalThreshold": 0.1,
            }
        )
        assert False
    except ValidationError:
        pass


def test_breached_and_renotify_window():
    assert breached(">=", 0.2, 0.1, 0.15) == "critical"
    assert breached(">=", 0.05, 0.1, 0.15) == ""
    now = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
    assert should_renotify(None, 5, now) is True
    assert should_renotify(now, 5, now + timedelta(minutes=4)) is False


def test_render_template_never_leaves_mustache():
    got = render_template(
        "[{{alert.severity}}] {{object.name}}={{alert.value}} {{missing.key}}",
        {"alert.severity": "critical", "object.name": "storefront"},
    )
    assert "{{" not in got
    assert "storefront" in got
    assert "—" in got


def test_monitor_crud_and_alert_events():
    control = MemoryControl()
    _seed_app(control)
    policies = MemoryPolicyStore()
    events = MemoryEventStore()
    service = MonitorsService(control=control, policies=policies, events=events)

    created = service.create_monitor(
        "tester",
        {
            "name": "Checkout errors",
            "application": "checkout",
            "organizations": [10],
            "metric": "error_rate",
            "warnThreshold": 0.05,
            "criticalThreshold": 0.1,
            "notificationTargets": [
                {
                    "channelId": 1,
                    "channelName": "mail",
                    "channelType": "email",
                    "deliveryMode": "message",
                    "recipientMode": "free_text",
                    "recipients": ["ops@example.test"],
                }
            ],
        },
        assignable_orgs={10},
    )
    assert created["id"]
    assert created["firing"] is False
    assert created["notificationTargets"][0]["channelId"] == 1
    assert len(service.list_monitors(visible_orgs={10})) == 1

    updated = service.update_monitor(
        "tester",
        created["id"],
        {
            "name": "Checkout errors",
            "application": "checkout",
            "organizations": [10],
            "metric": "error_rate",
            "warnThreshold": 0.05,
            "criticalThreshold": 0.2,
            "enabled": True,
        },
        assignable_orgs={10},
        visible_orgs={10},
    )
    assert updated["criticalThreshold"] == 0.2

    page = service.list_alert_events({"page": 1, "limit": 15}, visible_orgs={10})
    assert page["items"] == []
    assert page["total"] == 0

    service.delete_monitor(created["id"], visible_orgs={10})
    assert service.list_monitors(visible_orgs={10}) == []


def test_evaluator_fires_and_notifies():
    control = MemoryControl()
    _seed_app(control)
    policies = MemoryPolicyStore()
    events = MemoryEventStore()
    notifier = MemoryNotifier()
    service = MonitorsService(control=control, policies=policies, events=events)
    policy = service.create_monitor(
        "tester",
        {
            "name": "Checkout errors",
            "application": "checkout",
            "organizations": [10],
            "metric": "error_rate",
            "warnThreshold": 0.05,
            "criticalThreshold": 0.1,
            "forDurationSec": 0,
            "noDataAfter": 0,
            "notificationTargets": [
                {
                    "channelId": 7,
                    "channelName": "mail",
                    "channelType": "email",
                    "deliveryMode": "message",
                    "recipientMode": "free_text",
                    "recipients": ["ops@example.test"],
                }
            ],
        },
        assignable_orgs={10},
    )
    now = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
    result = AlertEvaluator(
        policies=policies,
        events=events,
        analytics=FakeAnalytics(0.5),
        notifier=notifier,
        now=lambda: now,
    ).evaluate_all()
    assert result["fired"] == 1
    assert events.latest_open(policy["id"])["status"] == "active"
    opened = events.latest_open(policy["id"])
    deliveries = events.list_deliveries(opened["id"])
    assert len(deliveries) == 1
    assert "Checkout errors" in deliveries[0]["body"]
    assert deliveries[0]["payload"]["alert_link"] == f"/rum/alert-events?event={opened['id']}"

    result = AlertEvaluator(
        policies=policies,
        events=events,
        analytics=FakeAnalytics(0.01),
        notifier=notifier,
        now=lambda: now + timedelta(minutes=1),
    ).evaluate_all()
    assert result["resolved"] == 1
    assert events.latest_open(policy["id"]) is None
    assert events.get_alert(opened["id"])["status"] == "recovered"


def test_evaluator_skips_without_analytics():
    result = AlertEvaluator(
        policies=MemoryPolicyStore(),
        events=MemoryEventStore(),
        analytics=UnavailableAnalytics(),
        notifier=MemoryNotifier(),
    ).evaluate_all()
    assert result["skipped"] is True
    assert result["reason"] == "analytics"
