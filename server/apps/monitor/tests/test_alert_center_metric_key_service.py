"""监控指标 key 经生命周期事件传入告警中心的契约。"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from apps.alerts.aggregation.builder.alert_builder import AlertBuilder
from apps.alerts.aggregation.recovery.match_key import build_recovery_match_key
from apps.alerts.common.source_adapter.constants import build_nats_source_config
from apps.alerts.common.source_adapter.nats import NatsAdapter
from apps.alerts.models import AlertSource, Event
from apps.alerts.notification_templates.events import event_row
from apps.alerts.notification_templates.renderer import render_source
from apps.monitor.models import Metric, MetricGroup, MonitorObject
from apps.monitor.services.alert_lifecycle_notify import AlertLifecycleNotifier

pytestmark = pytest.mark.unit


def _policy(query, policy_id=19):
    return SimpleNamespace(id=policy_id, name="内存策略", query_condition=query, organizations=[1])


def _alert():
    return SimpleNamespace(
        id=34,
        policy_id=19,
        content="内存使用率过高",
        level="warning",
        value=65.6,
        status="new",
        monitor_instance_id="('host-1',)",
        monitor_instance_name="host-1",
        metric_instance_id="('host-1',)",
        dimensions={"instance_id": "host-1"},
        start_event_time=datetime(2026, 9, 29, tzinfo=timezone.utc),
        end_event_time=None,
    )


@pytest.mark.parametrize("action", ["created", "upgraded", "recovered", "closed"])
def test_all_lifecycle_payloads_carry_metric_key(action):
    notifier = AlertLifecycleNotifier(_policy({"type": "metric", "metric_name": "mem_used_percent"}))
    payload = notifier._build_alert_center_payload(_alert(), action, "", "")
    assert payload.get("item") == "mem_used_percent"
    assert payload["labels"]["metric_instance_id"] == "('host-1',)"
    assert payload["external_id"] == "34"
    assert payload["monitor_id"] == "('host-1',)"


@pytest.mark.parametrize(
    "query",
    [None, {}, {"type": "metric", "metric_id": 999999}, {"type": "formula", "expression": "a / b"}, {"type": "pmq", "query": "up"}],
)
@pytest.mark.django_db
def test_unresolvable_metric_does_not_invent_a_key(query):
    payload = AlertLifecycleNotifier(_policy(query))._build_alert_center_payload(_alert(), "created", "", "")
    assert payload.get("item") == ""


@pytest.mark.django_db
def test_metric_id_lookup_is_shared_across_alerts_and_policies(django_assert_num_queries):
    obj = MonitorObject.objects.create(name="MetricKeyHost")
    group = MetricGroup.objects.create(name="memory", monitor_object=obj)
    metrics = [Metric.objects.create(name=name, monitor_object=obj, metric_group=group) for name in ("mem_used_percent", "cpu_usage")]
    policies = {19 + index: _policy({"type": "metric", "metric_id": metric.id}, 19 + index) for index, metric in enumerate(metrics)}
    notifier = AlertLifecycleNotifier(policies_by_id=policies)
    with django_assert_num_queries(1):
        for policy_id, expected in ((19, "mem_used_percent"), (20, "cpu_usage"), (19, "mem_used_percent")):
            alert = _alert()
            alert.policy_id = policy_id
            assert notifier._build_alert_center_payload(alert, "created", "", "").get("item") == expected


def test_metric_key_reaches_event_aggregation_and_notification_without_changing_identity(monkeypatch):
    source = AlertSource(id=1, name="NATS", source_id="nats", config=build_nats_source_config(), team_secrets={})
    monkeypatch.setattr(NatsAdapter, "get_event_level", staticmethod(lambda: ("3", ["0", "1", "2", "3"])))
    adapter = NatsAdapter(source, trusted_internal=True)
    notifier = AlertLifecycleNotifier(_policy({"type": "metric", "metric_name": "mem_used_percent"}))
    payload = notifier._build_alert_center_payload(_alert(), "created", "", "")
    payload["push_source_id"] = "lite-monitor"

    def to_event(data):
        event = Event(**adapter.mapping_fields_to_event(data))
        adapter.add_base_fields(event, data)
        return event

    event = to_event(payload)
    legacy_event = to_event({key: value for key, value in payload.items() if key != "item"})
    assert event.item == "mem_used_percent"
    assert event.ingest_key == legacy_event.ingest_key
    assert build_recovery_match_key(event) == build_recovery_match_key(legacy_event)
    assert AlertBuilder._resolve_standard_fields([event])["item"] == "mem_used_percent"
    result = render_source(
        "监控指标：{{ events.latest.item }}",
        {"events": {"latest": event_row(event, {}), "count": 1}},
        channel_type="email",
    )
    assert result.value == "监控指标：mem_used_percent"
