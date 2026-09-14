"""监控源条件组合、分批和输入契约。"""

import pytest
from django.utils import timezone

from apps.alerts.common.shield import EventShieldOperator
from apps.alerts.models import Alert, AlertShield, AlertSource, Event
from apps.alerts.serializers.assignment_shield import AlertAssignmentModelSerializer, AlertShieldModelSerializer
from apps.alerts.utils.monitor_source_rules import MonitorSourceRuleMatcher

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def rule(value, operator="any_of"):
    return {"key": "push_source_ids", "operator": operator, "value": [value] if isinstance(value, str) else value}


def test_array_conditions_preserve_and_or_across_candidate_batches():
    alerts = [
        Alert(
            alert_id=f"source-{index}",
            title="CPU" if index % 2 else "disk",
            level="1",
            content="",
            fingerprint=f"f-{index}",
            push_source_ids=["prod", "test"] if index % 2 else ["test"],
        )
        for index in range(205)
    ]
    Alert.objects.bulk_create(alerts)
    matcher = MonitorSourceRuleMatcher({"title": "title", "push_source_ids": "push_source_ids"}, source_field="push_source_ids")
    rules = [
        [rule("prod"), rule("test"), {"key": "title", "operator": "eq", "value": "CPU"}],
        [rule("test"), {"key": "title", "operator": "eq", "value": "disk"}],
    ]
    ids = matcher.filter_queryset(Alert.objects.all(), rules)
    assert len(ids) == len(set(ids)) == 205
    ids = matcher.filter_queryset(Alert.objects.all(), [[rule("prod"), rule("test")]])
    assert len(ids) == 102
    invalid = matcher.filter_queryset(Alert.objects.all(), [[rule([]), {"key": "title", "operator": "eq", "value": "CPU"}]])
    assert invalid == []


@pytest.mark.parametrize(
    "serializer_class,key", [(AlertAssignmentModelSerializer, "push_source_ids"), (AlertShieldModelSerializer, "push_source_id")]
)
@pytest.mark.parametrize("operator,value", [("eq", []), ("eq", 1), ("eq", "  "), ("re", "["), ("unknown", "prod"), ("eq", "x" * 257)])
def test_invalid_monitor_source_condition_is_rejected_on_save(serializer_class, key, operator, value):
    serializer = serializer_class(
        data={"name": "监控源条件", "match_type": "filter", "notify_channels": [], "match_rules": [[{"key": key, "operator": operator, "value": value}]]}
    )
    assert not serializer.is_valid()
    assert "match_rules" in serializer.errors


@pytest.mark.parametrize(
    "operator,value,expected",
    [
        ("any_of", ["prod"], {"prod"}),
        ("none_of", ["prod"], {"Prod-east", "test", "001", "1", "default"}),
        ("any_of", ["prod", "Prod-east"], {"prod", "Prod-east"}),
        ("none_of", ["prod", "Prod-east"], {"test", "001", "1", "default"}),
        ("any_of", ["001"], {"001"}),
        ("any_of", ["1"], {"1"}),
    ],
)
def test_shield_source_operators_use_scalar_identity_and_exclude_empty_values(operator, value, expected):
    source = AlertSource.objects.create(name="屏蔽边界", source_id="shield-boundary", source_type="restful", secret="test")
    events = [
        Event.objects.create(
            source=source,
            event_id=f"shield-boundary-{index}",
            title="CPU",
            level="1",
            raw_data={},
            start_time=timezone.now(),
            push_source_id=item,
        )
        for index, item in enumerate(["prod", "Prod-east", "test", "001", "1", "", "  ", "default"])
    ]
    outside = Event.objects.create(
        source=source, event_id="outside-input", title="CPU", level="1", raw_data={}, start_time=timezone.now(), push_source_id="prod"
    )
    AlertShield.objects.create(
        name="监控源", match_type="filter", suppression_time={}, match_rules=[[{"key": "push_source_id", "operator": operator, "value": value}]]
    )
    result = EventShieldOperator([event.event_id for event in events]).execute_shield_check()
    assert result["shielded_events"] == len(expected)
    assert set(Event.objects.filter(status="shield").values_list("push_source_id", flat=True)) == expected
    outside.refresh_from_db()
    assert outside.status != "shield"


@pytest.mark.parametrize(
    "serializer_class,key", [(AlertAssignmentModelSerializer, "push_source_ids"), (AlertShieldModelSerializer, "push_source_id")]
)
@pytest.mark.parametrize("value", ["源" * 256, "001", "default", 'source"with\\symbols'])
def test_valid_source_identifiers_round_trip_without_normalization(serializer_class, key, value):
    condition = {"key": key, "operator": "any_of", "value": [value]}
    serializer = serializer_class(data={"name": "边界值", "match_type": "filter", "match_rules": [[condition]]})
    assert serializer.is_valid(), serializer.errors
    saved = serializer.save()
    assert serializer_class(saved).data["match_rules"] == [[condition]]
