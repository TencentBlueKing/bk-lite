"""按产品字段矩阵验证保存、查询和内存执行的一致性。"""

import pytest
from django.utils import timezone

from apps.alerts.action.matcher import event_matches as alert_matches
from apps.alerts.action.payload import build_rule_payload as build_match_payload
from apps.alerts.aggregation.strategy.instant_matcher import InstantMatcher
from apps.alerts.aggregation.strategy.matcher import StrategyMatcher
from apps.alerts.common.assignment import AlertAssignmentOperator
from apps.alerts.common.shield import EventShieldOperator
from apps.alerts.enrichment.matcher import event_matches
from apps.alerts.models import Alert, AlertSource, Event
from apps.alerts.serializers.action import ActionRuleSerializer
from apps.alerts.serializers.assignment_shield import AlertAssignmentModelSerializer, AlertShieldModelSerializer
from apps.alerts.serializers.enrichment import EnrichmentRuleModelSerializer
from apps.alerts.serializers.strategy import AlarmStrategySerializer
from apps.alerts.utils.monitor_source_rules import MonitorSourceRuleMatcher

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

TEXT_FIELDS = ["title", "content", "description"]
CANDIDATE_FIELDS = ["resource_type", "resource_id", "push_source_id", "source_name", "level"]
MIXED_FIELDS = ["resource_name", "item", "service", "location"]
CASES = [(field, op) for field in TEXT_FIELDS for op in ["eq", "ne", "contains", "not_contains"]]
CASES += [(field, op) for field in CANDIDATE_FIELDS for op in ["any_of", "none_of"]]
CASES += [(field, op) for field in MIXED_FIELDS for op in ["any_of", "none_of", "contains", "not_contains", "re"]]
CASES += [(field, op) for field in ["push_source_ids", "source_names"] for op in ["any_of", "all_of", "none_of"]]
SERIALIZERS = {
    "correlation": AlarmStrategySerializer,
    "shield": AlertShieldModelSerializer,
    "enrichment": EnrichmentRuleModelSerializer,
    "assignment": AlertAssignmentModelSerializer,
    "action": ActionRuleSerializer,
}


@pytest.fixture
def records():
    from apps.alerts.models.models import Level

    Level.objects.bulk_create(
        [Level(level_type=scope, level_id=i, level_name=str(i), level_display_name=str(i)) for scope in ["event", "alert"] for i in [1, 2, 3]]
    )
    events, alerts, payloads = [], [], []
    for index, text in enumerate(["alpha beta", "alpha", "gamma", ""]):
        source = AlertSource.objects.create(name=text, source_id=f"matrix-{index}", source_type="restful", secret="test")
        data = dict(
            title=text,
            description=text,
            resource_type=text,
            resource_id=text,
            resource_name=text,
            item=text,
            service=text,
            location=text,
            push_source_id=text,
            level=["1", "2", "3", ""][index],
        )
        event = Event.objects.create(source=source, event_id=f"matrix-{index}", start_time=timezone.now(), raw_data={}, **data)
        alert = Alert.objects.create(
            alert_id=f"matrix-{index}",
            fingerprint=f"matrix-{index}",
            title=text,
            content=text,
            level=data["level"],
            source_name=text,
            resource_type=text,
            resource_id=text,
            resource_name=text,
            item=text,
            push_source_ids=[["alpha", "beta", "delta"], ["alpha"], ["gamma"], []][index],
        )
        alert.events.add(event)
        events.append(event)
        alerts.append(alert)
        payloads.append({**data, "content": text, "source_id": source.pk, "source_name": text})
    return events, alerts, payloads


@pytest.mark.parametrize("key,operator", CASES)
def test_every_advertised_field_operator_can_be_saved_and_matches_correct_records(records, key, operator):
    events, alerts, payloads = records
    values = "alpha" if operator in {"contains", "not_contains"} else "^alpha" if operator == "re" else "alpha beta"
    expected = {0} if operator == "eq" else {1, 2} if operator == "ne" else {2} if operator == "not_contains" else {0, 1}
    if key == "push_source_ids":
        values = ["alpha", "beta"]
        expected = {0, 1} if operator == "any_of" else {0} if operator == "all_of" else {2}
    if operator in {"any_of", "none_of", "all_of"} and key != "push_source_ids":
        values = ["1", "2"] if key == "level" else ["alpha beta", "alpha"]
        expected = {0, 1} if operator == "any_of" else {2} if operator == "none_of" else set()
    rules = [[{"key": key, "operator": operator, "value": values}]]
    scopes = ["correlation", "shield", "enrichment"] if key not in {"push_source_ids", "content", "source_names"} else []
    if key not in {"service", "location", "push_source_id", "source_name", "description"}:
        scopes += ["assignment", "action"]
    for scope in scopes:
        serializer = SERIALIZERS[scope](
            data={
                "name": "matrix",
                "strategy_type": "smart_denoise",
                "match_rules": rules,
                "input_binding": {"model_id": "resource_type", "inst_uuid": "resource_id"},
            },
            partial=True,
        )
        assert serializer.is_valid(), (scope, serializer.errors)
    if "correlation" in scopes:
        assert set(StrategyMatcher.match_events_to_strategy(Event.objects.all(), rules).values_list("pk", flat=True)) == {
            events[i].pk for i in expected
        }
        assert {i for i, event in enumerate(events) if InstantMatcher.match_in_memory(event, rules)} == expected
        matcher = MonitorSourceRuleMatcher(EventShieldOperator.FIELD_MAPPING, source_field="push_source_id")
        assert set(matcher.filter_queryset(Event.objects.all(), rules)) == {events[i].pk for i in expected}
        assert {i for i, payload in enumerate(payloads) if event_matches(payload, rules)} == expected
    if "assignment" in scopes:
        matcher = MonitorSourceRuleMatcher(AlertAssignmentOperator.FIELD_MAPPING, source_field="push_source_ids")
        assert set(matcher.filter_queryset(Alert.objects.all(), rules)) == {alerts[i].pk for i in expected}
        assert {i for i, alert in enumerate(alerts) if alert_matches(build_match_payload(alert), rules)} == expected


@pytest.mark.parametrize("serializer_class", list(SERIALIZERS.values()))
@pytest.mark.parametrize(
    "kind,valid",
    [
        ("20_groups", True),
        ("21_groups", False),
        ("100_conditions", True),
        ("101_conditions", False),
        ("empty_group", False),
        ("unknown_field", False),
    ],
)
def test_rule_size_and_structure_are_enforced_at_every_write_boundary(serializer_class, kind, valid):
    condition = {"key": "title", "operator": "eq", "value": "host-a"}
    rules = {
        "20_groups": [[condition] for _ in range(20)],
        "21_groups": [[condition] for _ in range(21)],
        "100_conditions": [[condition] * 100],
        "101_conditions": [[condition] * 101],
        "empty_group": [[]],
        "unknown_field": [[condition, {"key": "nonexistent", "operator": "any_of", "value": ["a"]}]],
    }[kind]
    serializer = serializer_class(
        data={
            "name": "limits",
            "strategy_type": "smart_denoise",
            "match_rules": rules,
            "input_binding": {"model_id": "resource_type", "inst_uuid": "resource_id"},
        },
        partial=True,
    )
    assert serializer.is_valid() is valid, serializer.errors
    if not valid:
        assert "match_rules" in serializer.errors


def test_list_and_or_rules_preserve_team_scope_across_real_candidate_batches():
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from apps.alerts.utils.permission_scope import apply_team_scope_with_group_ids

    matching = Alert.objects.bulk_create(
        [
            Alert(alert_id=f"batch-{i}", fingerprint=f"batch-{i}", title="CPU", content="", level="1", team=[1], push_source_ids=["a", "b", "extra"])
            for i in range(201)
        ]
    )
    partial = Alert.objects.create(alert_id="partial", fingerprint="partial", title="CPU", content="", level="1", team=[1], push_source_ids=["a"])
    alternative = Alert.objects.create(
        alert_id="alternative", fingerprint="alternative", title="CPU", content="", level="1", team=[1], resource_name="blue", push_source_ids=[]
    )
    foreign = Alert.objects.create(
        alert_id="foreign", fingerprint="foreign", title="CPU", content="", level="1", team=[2], resource_name="blue", push_source_ids=["a", "b"]
    )
    rules = [
        [{"key": "push_source_ids", "operator": "all_of", "value": ["a", "b"]}, {"key": "level", "operator": "any_of", "value": ["1"]}],
        [{"key": "resource_name", "operator": "any_of", "value": ["blue"]}],
    ]
    with CaptureQueriesContext(connection) as queries:
        candidates = apply_team_scope_with_group_ids(Alert.objects.all(), [1])
        actual = MonitorSourceRuleMatcher(AlertAssignmentOperator.FIELD_MAPPING, source_field="push_source_ids").filter_queryset(candidates, rules)
    assert set(actual) == {alert.pk for alert in matching} | {alternative.pk}
    assert partial.pk not in actual and foreign.pk not in actual
    assert len(actual) == 202
    assert len(queries) <= 10  # 203 个组织内候选跨两批；不应逐告警发查询。


@pytest.mark.parametrize("value,expected", [("0", {0}), ("001", {1}), ("1", {2})])
def test_exact_identity_keeps_zero_leading_zeros_and_duplicate_candidates(value, expected):
    alerts = [
        Alert.objects.create(alert_id=f"identity-{i}", fingerprint=f"identity-{i}", title="CPU", content="", level="1", resource_id=item)
        for i, item in enumerate(["0", "001", "1", ""])
    ]
    rules = [[{"key": "resource_id", "operator": "any_of", "value": [value, value]}]]
    matcher = MonitorSourceRuleMatcher(AlertAssignmentOperator.FIELD_MAPPING, source_field="push_source_ids")
    assert set(matcher.filter_queryset(Alert.objects.all(), rules)) == {alerts[i].pk for i in expected}
    assert {i for i, alert in enumerate(alerts) if alert_matches(build_match_payload(alert), rules)} == expected
