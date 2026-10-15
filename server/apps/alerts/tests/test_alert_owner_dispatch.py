import pytest
from rest_framework.exceptions import ValidationError

from apps.alerts.aggregation.builder.alert_builder import AlertBuilder
from apps.alerts.common.assignment import execute_auto_assignment_for_alerts
from apps.alerts.common.source_adapter.restful import RestFulAdapter
from apps.alerts.constants.constants import LevelType
from apps.alerts.enrichment.providers.base import EnrichmentProvider, register_provider
from apps.alerts.models import Alert, AlertAssignment, EnrichmentRule, Event
from apps.alerts.models.alert_operator import AlarmStrategy
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Level
from apps.alerts.models.operator_log import OperatorLog
from apps.alerts.serializers.assignment_shield import AlertAssignmentModelSerializer
from apps.system_mgmt.models import Group, User


def _user(username, *, disabled=False, group_ids=None):
    return User.objects.create(
        username=username,
        display_name=username,
        email=f"{username}@example.com",
        password="x",
        disabled=disabled,
        group_list=group_ids or [],
    )


def _alert(alert_id, owners):
    return Alert.objects.create(
        alert_id=alert_id,
        status="unassigned",
        level="1",
        title=alert_id,
        content="content",
        fingerprint=alert_id,
        owners=owners,
    )


def _assignment(name, target):
    personnel = target.get("usernames") or []
    return AlertAssignment.objects.create(
        name=name,
        match_type="all",
        personnel=personnel,
        config={"notification_target": target},
        is_active=True,
    )


@pytest.fixture
def silence_fallback_notice(monkeypatch):
    monkeypatch.setattr("apps.alerts.common.assignment.not_assignment_alert_notify", lambda alert_ids: None)


@pytest.mark.django_db
def test_assignment_without_prefer_ignores_alert_owners(silence_fallback_notice):
    _user("alice")
    _user("fallback")
    alert = _alert("ALERT-LEGACY", ["alice"])
    _assignment(
        "legacy",
        {"type": "user", "usernames": ["fallback"]},
    )
    execute_auto_assignment_for_alerts([alert.alert_id])
    alert.refresh_from_db()
    assert alert.operator == ["fallback"]


@pytest.mark.django_db
def test_prefer_owner_notifies_owner_not_fallback(silence_fallback_notice):
    _user("alice")
    _user("fallback")
    alert = _alert("ALERT-OWNER", ["alice"])
    assignment = _assignment(
        "prefer",
        {"type": "user", "usernames": ["fallback"], "prefer_alert_owner": True},
    )
    execute_auto_assignment_for_alerts([alert.alert_id])
    alert.refresh_from_db()
    assert alert.operator == ["alice"]
    overview = OperatorLog.objects.get(target_id=alert.pk).overview
    assert "命中责任人" in overview
    assert "人数 1" in overview
    assert "alice" not in overview
    assert "fallback" not in overview
    assert str(assignment.id) in overview


@pytest.mark.django_db
def test_empty_or_disabled_owners_use_page_fallback(silence_fallback_notice):
    _user("disabled-owner", disabled=True)
    _user("fallback")
    empty_alert = _alert("ALERT-EMPTY", [])
    disabled_alert = _alert("ALERT-DISABLED", ["disabled-owner"])
    _assignment(
        "fallback-page",
        {"type": "user", "usernames": ["fallback"], "prefer_alert_owner": True},
    )
    execute_auto_assignment_for_alerts([empty_alert.alert_id, disabled_alert.alert_id])
    empty_alert.refresh_from_db()
    disabled_alert.refresh_from_db()
    assert empty_alert.operator == ["fallback"]
    assert disabled_alert.operator == ["fallback"]
    assert OperatorLog.objects.filter(overview__contains="命中兜底").count() == 2


@pytest.mark.django_db
def test_same_batch_assigns_each_alert_its_own_owner(silence_fallback_notice):
    _user("alice")
    _user("bob")
    _user("fallback")
    first = _alert("ALERT-A", ["alice"])
    second = _alert("ALERT-B", ["bob"])
    _assignment(
        "batch",
        {"type": "user", "usernames": ["fallback"], "prefer_alert_owner": True},
    )
    execute_auto_assignment_for_alerts([first.alert_id, second.alert_id])
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.operator == ["alice"]
    assert second.operator == ["bob"]


@pytest.mark.django_db
def test_organization_fallback_is_used_when_alert_has_no_owner(silence_fallback_notice):
    group = Group.objects.create(name="值班组")
    _user("noc", group_ids=[group.id])
    alert = _alert("ALERT-ORG", [])
    _assignment(
        "org-fallback",
        {
            "type": "organization",
            "organization_ids": [group.id],
            "include_children": False,
            "prefer_alert_owner": True,
        },
    )
    execute_auto_assignment_for_alerts([alert.alert_id])
    alert.refresh_from_db()
    assert alert.operator == ["noc"]


@pytest.mark.django_db
def test_empty_fallback_leaves_alert_unassigned(monkeypatch):
    notified = []
    monkeypatch.setattr(
        "apps.alerts.common.assignment.not_assignment_alert_notify",
        lambda alert_ids: notified.append(set(alert_ids)),
    )
    alert = _alert("ALERT-NONE", [])
    _assignment(
        "empty-fallback",
        {"type": "user", "usernames": ["missing-user"], "prefer_alert_owner": True},
    )
    execute_auto_assignment_for_alerts([alert.alert_id])
    alert.refresh_from_db()
    assert alert.status == "unassigned"
    assert alert.operator == []
    assert notified == [{alert.alert_id}]


@pytest.mark.django_db
def test_prefer_alert_owner_requires_fallback_and_rejects_escalation_flag():
    _user("fallback")
    saved = AlertAssignmentModelSerializer(
        data={
            "name": "保存开关",
            "match_type": "all",
            "match_rules": [],
            "personnel": [],
            "notify_channels": [],
            "notification_scenario": [],
            "config": {
                "notification_target": {
                    "type": "user",
                    "usernames": ["fallback"],
                    "prefer_alert_owner": True,
                }
            },
            "priority": 100,
            "is_active": True,
        }
    )
    assert saved.is_valid(), saved.errors
    assert saved.validated_data["config"]["notification_target"]["prefer_alert_owner"] is True

    missing_fallback = AlertAssignmentModelSerializer(
        data={
            "name": "缺少兜底",
            "match_type": "all",
            "match_rules": [],
            "personnel": [],
            "notify_channels": [],
            "notification_scenario": [],
            "config": {
                "notification_target": {
                    "type": "user",
                    "usernames": [],
                    "prefer_alert_owner": True,
                }
            },
            "priority": 100,
            "is_active": True,
        }
    )
    assert missing_fallback.is_valid() is False

    escalation = AlertAssignmentModelSerializer(
        data={
            "name": "升级拒绝",
            "match_type": "all",
            "match_rules": [],
            "personnel": ["fallback"],
            "notify_channels": [],
            "notification_scenario": [],
            "config": {
                "notification_target": {"type": "user", "usernames": ["fallback"]},
                "escalation": {
                    "enabled": True,
                    "mode": "append",
                    "layers": [
                        {
                            "personnel": ["fallback"],
                            "wait_minutes": 5,
                            "notification_target": {
                                "type": "user",
                                "usernames": ["fallback"],
                                "prefer_alert_owner": True,
                            },
                        }
                    ],
                },
            },
            "priority": 100,
            "is_active": True,
        }
    )
    assert escalation.is_valid() is False
    assert "升级层不支持" in str(escalation.errors)
    with pytest.raises(ValidationError):
        AlertAssignmentModelSerializer()._read_prefer_alert_owner({"prefer_alert_owner": "yes"})


@register_provider
class _FlowOwnerProvider(EnrichmentProvider):
    provider_type = "owner_flow_test"

    def fetch_batch(self, keys, config):
        records = {
            "host-enriched": [{"operator": [1]}],
            "host-empty": [{"inst_name": "clb"}],
        }
        return {key: records.get(dict(key).get("inst_uuid"), []) for key in keys}


@pytest.mark.django_db
def test_ingress_enrichment_aggregation_and_dispatch_cover_three_owner_paths(monkeypatch, silence_fallback_notice):
    for level_type in (LevelType.EVENT, LevelType.ALERT):
        for level_id in (0, 1, 2, 3):
            Level.objects.create(
                level_id=level_id,
                level_name=f"{level_type}-{level_id}",
                level_display_name=f"{level_type}-{level_id}",
                level_type=level_type,
            )
    _user("alice")
    _user("zoe")
    _user("noc")
    monkeypatch.setattr(
        "apps.alerts.enrichment.owners.resolve_active_usernames",
        lambda user_ids: {1: "alice"} if 1 in user_ids else {},
    )
    source = AlertSource.objects.create(
        name="责任人源",
        source_id="owner-flow",
        source_type="restful",
        secret="src-secret",
        config={
            "event_fields_mapping": {
                "title": "title",
                "level": "level",
                "resource_id": "resource_id",
                "resource_type": "resource_type",
                "assignee": "assignee",
            }
        },
    )
    EnrichmentRule.objects.create(
        name="责任人映射",
        is_active=True,
        match_rules=[],
        provider_type="owner_flow_test",
        input_binding={"model_id": "resource_type", "inst_uuid": "resource_id"},
        provider_config={"owner_fields": ["operator"]},
        output_projection=[{"source": "inst_name"}],
        on_multiple="first",
        namespace="cmdb_owner",
        team=[1],
    )
    _assignment(
        "flow-prefer",
        {"type": "user", "usernames": ["noc"], "prefer_alert_owner": True},
    )
    strategy = AlarmStrategy.objects.create(
        name="flow-strategy",
        strategy_type="smart_denoise",
        team=[1],
        dispatch_team=[1],
        params={"window_size": 10},
    )
    adapter = RestFulAdapter(alert_source=source)
    adapter.resolved_team = [1]
    adapter.create_events(
        [
            {"title": "丰富替换", "level": "1", "resource_type": "host", "resource_id": "host-enriched", "assignee": ["zoe"]},
            {"title": "保留上报", "level": "1", "resource_type": "host", "resource_id": "host-empty", "assignee": ["zoe"]},
            {"title": "走兜底", "level": "1", "resource_type": "host", "resource_id": "host-missing"},
        ]
    )
    alerts = []
    from django.db import transaction

    with transaction.atomic():
        for event in Event.objects.order_by("id"):
            alerts.append(
                AlertBuilder.create_or_update_alert(
                    {
                        "fingerprint": f"fp-{event.event_id}",
                        "event_ids": [event.event_id],
                        "alert_level": "1",
                        "alert_title": event.title,
                        "alert_description": event.title,
                        "first_event_time": event.start_time,
                        "last_event_time": event.start_time,
                    },
                    strategy,
                )
            )
    by_title = {alert.title: alert for alert in alerts}
    assert by_title["丰富替换"].owners == ["alice"]
    assert by_title["保留上报"].owners == ["zoe"]
    assert by_title["走兜底"].owners == []

    execute_auto_assignment_for_alerts([alert.alert_id for alert in alerts])
    for alert in alerts:
        alert.refresh_from_db()
    assert by_title["丰富替换"].operator == ["alice"]
    assert by_title["保留上报"].operator == ["zoe"]
    assert by_title["走兜底"].operator == ["noc"]
