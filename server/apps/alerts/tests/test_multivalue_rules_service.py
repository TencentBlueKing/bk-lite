"""区分实际字段类型与候选数组，未知/旧条件整条拒绝。"""
import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.alerts.action.matcher import event_matches as alert_matches
from apps.alerts.action.payload import build_match_payload
from apps.alerts.aggregation.strategy.instant_matcher import InstantMatcher
from apps.alerts.aggregation.strategy.matcher import StrategyMatcher
from apps.alerts.enrichment.matcher import event_matches
from apps.alerts.models import Alert, AlertSource, Event
from apps.alerts.utils.monitor_source_rules import MonitorSourceRuleMatcher
from apps.alerts.utils.rule_catalog import FIELDS, validate_rules_for_serializer

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize("operator,expected", [("any_of", {0, 1}), ("all_of", {0}), ("none_of", {2})])
def test_list_membership_identical_between_assignment_and_action(operator, expected):
    rules = [[{"key": "push_source_ids", "operator": operator, "value": ["a", "b", "a"]}]]
    values = [["a", "b", "v", "d"], ["a"], ["v", "d"], [], [""], "a", [1]]
    alerts = [
        Alert.objects.create(alert_id=f"list-{i}", fingerprint=f"list-{i}", title="CPU", content="", level="1", push_source_ids=value)
        for i, value in enumerate(values)
    ]
    matcher = MonitorSourceRuleMatcher({}, source_field="push_source_ids")
    assert set(matcher.filter_queryset(Alert.objects.all(), rules)) == {alerts[i].pk for i in expected}
    assert {i for i, alert in enumerate(alerts) if alert_matches(build_match_payload(alert), rules)} == expected


@pytest.mark.parametrize("scope", ["correlation", "shield", "enrichment", "assignment", "action"])
@pytest.mark.parametrize(
    "condition",
    [
        {"key": "title", "operator": "any_of", "value": ["CPU"]},
        {"key": "title", "operator": "eq", "value": ["CPU"]},
        {"key": "title", "operator": "eq", "value": 1},
        {"key": "title", "operator": "text_any", "value": ["CPU"]},
        {"key": "title", "value": "CPU"},
        {"key": "标题", "operator": "包含", "value": "CPU"},
        {"key": "level_id", "operator": "eq", "value": "1"},
        {"key": "source_pk", "operator": "eq", "value": 1},
        {"key": "level", "operator": "eq", "value": ["1", "2"]},
        {"key": "level", "operator": "contains", "value": "1"},
        {"key": "level", "operator": "eq", "value": 1},
        {"key": "title", "operator": "re", "value": "["},
    ],
)
def test_invalid_types_and_legacy_rules_are_rejected_at_save_and_execution(scope, condition):
    rules = [[condition], [{"key": "title", "operator": "eq", "value": "CPU"}]]
    with pytest.raises(ValidationError):
        validate_rules_for_serializer(rules, scope)
    matcher = alert_matches if scope in {"assignment", "action"} else event_matches
    assert not matcher({"title": "CPU", "level": "1"}, rules)


@pytest.mark.parametrize("scope", ["assignment", "action"])
@pytest.mark.parametrize("value", [[], [""], ["  "], [1], [True], ["a"] * 51, ["x" * 257], "a", None])
def test_list_values_have_bounded_strict_string_elements(scope, value):
    with pytest.raises(ValidationError):
        validate_rules_for_serializer([[{"key": "push_source_ids", "operator": "any_of", "value": value}]], scope)


@pytest.mark.parametrize("scope", ["correlation", "shield", "enrichment"])
@pytest.mark.parametrize("value", ["1", True, 1.5, 0, -1, [1], None])
def test_event_foreign_key_requires_positive_integer(scope, value):
    with pytest.raises(ValidationError):
        validate_rules_for_serializer([[{"key": "source_id", "operator": "eq", "value": value}]], scope)


def test_foreign_primary_key_does_not_match_business_code_or_source_name():
    source = AlertSource.objects.create(name="Named source", source_id="999", source_type="restful", secret="test")
    event = Event.objects.create(source=source, event_id="identity", title="CPU", level="1", raw_data={}, start_time=timezone.now())
    for value, expected in [(source.pk, False), (999, False), ("999", False), ("Named source", False)]:
        rules = [[{"key": "source_id", "operator": "eq", "value": value}]]
        assert StrategyMatcher.match_events_to_strategy(Event.objects.all(), rules).exists() is expected
        assert InstantMatcher.match_in_memory(event, rules) is expected
        assert event_matches({"source_id": source.pk}, rules) is expected


def test_catalog_tracks_current_models_and_no_aliases():
    from apps.alerts.utils.rule_catalog import model_fields

    assert not {"source_pk", "level_id", "标题"} & FIELDS.keys()
    for model, scope in [(Event, "correlation"), (Alert, "assignment")]:
        for key, field in model_fields(scope).items():
            if key == "source_names":
                assert scope == "assignment" and FIELDS[key]["resolver"] == "alert_sources"
                continue
            if field == "source__name":
                assert model is Event
                AlertSource._meta.get_field("name")
                continue
            model._meta.get_field(field)
    assert "source_id" not in model_fields("action")
    assert "source_name" in model_fields("enrichment")
    assert "description" in model_fields("enrichment") and "content" not in model_fields("enrichment")
