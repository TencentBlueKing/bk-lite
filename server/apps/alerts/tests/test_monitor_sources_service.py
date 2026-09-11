"""监控源经过建警、关联、规则与查询接口的行为契约。"""

from types import SimpleNamespace

import pytest
from django.db import transaction
from django.utils import timezone

from apps.alerts.aggregation.builder.alert_builder import AlertBuilder
from apps.alerts.aggregation.processor.instant_dispatcher import InstantAlertDispatcher, InstantStrategyCache
from apps.alerts.aggregation.recovery.recovery_handler import RecoveryHandler
from apps.alerts.common.assignment import AlertAssignmentOperator
from apps.alerts.common.shield import EventShieldOperator
from apps.alerts.constants.constants import EventAction, LevelType
from apps.alerts.models import AlarmStrategy, Alert, AlertSource, Event, Level
from apps.alerts.models.alert_operator import AlertAssignment, AlertShield
from apps.alerts.serializers.alert import AlertModelSerializer
from apps.alerts.service.related_alerts import RelatedAlertsService
from apps.system_mgmt.models.user import User

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def context():
    AlertBuilder.clear_event_cache()
    AlertBuilder._valid_alert_levels = None
    Level.objects.create(level_id=1, level_name="error", level_display_name="错误", level_type=LevelType.ALERT)
    source = AlertSource.objects.create(name="监控", source_id="monitor-sources", source_type="nats", secret="test")
    strategy = AlarmStrategy.objects.create(name="监控源聚合", strategy_type="smart_denoise", dispatch_team=[1], params={"window_size": 10})
    yield source, strategy
    AlertBuilder.clear_event_cache()
    AlertBuilder._valid_alert_levels = None


def make_event(source, event_id, push_source_id, **overrides):
    values = dict(
        source=source,
        event_id=event_id,
        push_source_id=push_source_id,
        raw_data={},
        title="CPU high",
        description="CPU high",
        level="1",
        start_time=timezone.now(),
        item="cpu",
        resource_name="host1",
    )
    values.update(overrides)
    return Event.objects.create(**values)


def build_alert(strategy, events):
    now = timezone.now()
    with transaction.atomic():
        return AlertBuilder.create_or_update_alert(
            {
                "fingerprint": "monitor-sources-fingerprint",
                "event_ids": [event.event_id for event in events],
                "alert_level": "1",
                "alert_title": "监控源告警",
                "first_event_time": now,
                "last_event_time": now,
            },
            strategy,
        )


def test_aggregation_stores_deduplicated_sources_and_preserves_earlier_members(context):
    source, strategy = context
    events = [make_event(source, f"E-{index}", value) for index, value in enumerate(["prod", "001", "prod", "1", "", "default"])]
    alert = build_alert(strategy, events)
    alert.refresh_from_db()
    assert alert.push_source_ids == ["001", "1", "default", "prod"]

    updated = build_alert(strategy, [make_event(source, "E-next", "test")])
    updated.refresh_from_db()
    assert updated.pk == alert.pk
    assert updated.push_source_ids == ["001", "1", "default", "prod", "test"]
    repeated = build_alert(strategy, events)
    repeated.refresh_from_db()
    assert repeated.push_source_ids == ["001", "1", "default", "prod", "test"]
    assert repeated.events.count() == 7


def test_instant_alert_preserves_source(context):
    source, strategy = context
    strategy.strategy_type = "instant"
    strategy.team = [1]
    strategy.match_rules = [[{"key": "title", "operator": "contains", "value": "CPU"}]]
    strategy.save()
    event = make_event(source, "E-instant", "k8s-prod", team=[1])
    InstantStrategyCache.cache_clear()
    try:
        InstantAlertDispatcher.dispatch([[event]])
        alert = Alert.objects.get(events=event)
        assert alert.push_source_ids == ["k8s-prod"]
    finally:
        InstantStrategyCache.cache_clear()


def test_recovery_fallback_appends_source_and_is_idempotent(context):
    source, strategy = context
    created = make_event(source, "E-created", "prod", external_id="external-1", action=EventAction.CREATED)
    alert = build_alert(strategy, [created])
    recovery = make_event(source, "E-recovered", "recovery-bridge", external_id="external-1", action=EventAction.RECOVERY)
    RecoveryHandler.handle_recovery_events([recovery])
    RecoveryHandler.handle_recovery_events([recovery])
    alert.refresh_from_db()
    assert alert.push_source_ids == ["prod", "recovery-bridge"]
    assert alert.events.count() == 2


@pytest.mark.parametrize(
    "operator,value,expected",
    [
        ("any_of", ["prod"], ["mixed", "prod"]),
        ("none_of", ["prod"], ["test", "numeric"]),
        ("all_of", ["prod", "test"], ["mixed"]),
        ("any_of", ["1"], []),
        ("any_of", ["001"], ["numeric"]),
        ("eq", "prod", []),
        ("contains", "PRO", []),
        ("re", "^prod$", []),
    ],
)
def test_assignment_matches_source_elements(operator, value, expected):
    User.objects.create(username="source-op", domain="domain.com", group_list=[{"id": 1}])
    rows = {"mixed": ["prod", "test"], "prod": ["prod"], "test": ["test"], "empty": [], "numeric": ["001"]}
    for name, sources in rows.items():
        Alert.objects.create(alert_id=name, title="CPU", content="", level="1", fingerprint=name, push_source_ids=sources, team=[1])
    Alert.objects.create(alert_id="outside", title="CPU", content="", level="1", fingerprint="outside", push_source_ids=["prod"])
    AlertAssignment.objects.create(
        name="来源分派",
        match_type="filter",
        match_rules=[[{"key": "push_source_ids", "operator": operator, "value": value}]],
        personnel=["source-op"],
        config={},
        notify_channels=[],
        notification_scenario=[],
        notification_frequency={},
    )
    result = AlertAssignmentOperator(list(rows)).execute_auto_assignment()
    assert result["assigned_alerts"] == len(expected)
    assert set(Alert.objects.filter(status="pending").values_list("alert_id", flat=True)) == set(expected)


def test_shield_matches_source_before_instant_alert_creation(context):
    source, strategy = context
    prod = make_event(source, "E-prod", "prod")
    test = make_event(source, "E-test", "test")
    AlertShield.objects.create(
        name="来源屏蔽", match_type="filter", match_rules=[[{"key": "push_source_id", "operator": "any_of", "value": ["prod"]}]], suppression_time={}
    )
    result = EventShieldOperator([prod.event_id, test.event_id]).execute_shield_check()
    prod.refresh_from_db()
    test.refresh_from_db()
    assert result["shielded_events"] == 1
    assert prod.status == "shield"
    assert test.status != "shield"
    strategy.strategy_type = "instant"
    strategy.match_rules = [[{"key": "title", "operator": "contains", "value": "CPU"}]]
    strategy.save()
    InstantStrategyCache.cache_clear()
    try:
        InstantAlertDispatcher.dispatch([[prod, test]])
        assert not Alert.objects.filter(events=prod).exists()
        assert Alert.objects.get(events=test).push_source_ids == ["test"]
    finally:
        InstantStrategyCache.cache_clear()


def test_monitor_sources_are_read_only_and_available_in_related_details(context, monkeypatch):
    source, strategy = context
    alert = build_alert(strategy, [make_event(source, "E-detail", "prod")])
    monkeypatch.setattr("apps.core.utils.serializers.get_permission_rules", lambda *args: {"team": [1], "instance": []})
    request = SimpleNamespace(COOKIES={"current_team": "1"}, user=SimpleNamespace(is_superuser=True))
    serializer = AlertModelSerializer(alert, data={"push_source_ids": ["forged"]}, partial=True, context={"request": request})
    assert serializer.is_valid(), serializer.errors
    serializer.save()
    assert serializer.data["push_source_ids"] == ["prod"]
    alert.dimensions = {"item": "cpu"}
    alert.save(update_fields=["dimensions"])
    other = Alert.objects.create(
        alert_id="related", title="CPU", content="", level="1", fingerprint="related", team=[1], push_source_ids=["test"], dimensions={"item": "cpu"}
    )
    Alert.objects.create(
        alert_id="other-team",
        title="CPU",
        content="",
        level="1",
        fingerprint="other-team",
        team=[2],
        push_source_ids=["private"],
        dimensions={"item": "cpu"},
    )
    result = RelatedAlertsService.find_related_alerts(alert, group_ids=[1])
    assert [(item["id"], item["push_source_ids"]) for item in result["items"]] == [(other.pk, ["test"])]


@pytest.mark.parametrize("entry", ["aggregation", "recovery"])
def test_event_link_and_source_snapshot_rollback_together_and_can_be_retried(context, entry):
    source, strategy = context
    first = make_event(source, "rollback-first", "prod", external_id="rollback-external")
    alert = build_alert(strategy, [first])
    added = make_event(
        source,
        "rollback-next",
        "bridge",
        external_id="rollback-external",
        action=EventAction.CREATED if entry == "aggregation" else EventAction.RECOVERY,
    )

    def associate():
        if entry == "aggregation":
            build_alert(strategy, [added])
        else:
            RecoveryHandler.handle_recovery_events([added])

    with pytest.raises(RuntimeError, match="abort enclosing transaction"):
        with transaction.atomic():
            associate()
            raise RuntimeError("abort enclosing transaction")
    alert.refresh_from_db()
    assert alert.push_source_ids == ["prod"]
    assert list(alert.events.values_list("event_id", flat=True)) == ["rollback-first"]
    associate()
    alert.refresh_from_db()
    assert alert.push_source_ids == ["bridge", "prod"]
    assert set(alert.events.values_list("event_id", flat=True)) == {"rollback-first", "rollback-next"}
