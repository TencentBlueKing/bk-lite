"""告警源按完整名称匹配，恢复事件不贡献 Alert 来源。"""
import pytest
from django.utils import timezone

from apps.alerts.models import Alert, AlertSource, Event
from apps.alerts.utils.monitor_source_rules import MonitorSourceRuleMatcher

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def make_event(name, action="created"):
    source = AlertSource.objects.create(name=name, source_id=f"source-{Event.objects.count()}", source_type="restful", secret="test")
    return Event.objects.create(
        source=source, event_id=f"event-{source.pk}", title="CPU", level="1", action=action, start_time=timezone.now(), raw_data={}
    )


@pytest.mark.parametrize(
    "operator,values,expected",
    [
        ("any_of", ["B", "C"], True),
        ("any_of", ["C"], False),
        ("all_of", ["A", "B", "A"], True),
        ("all_of", ["A", "C"], False),
        ("none_of", ["C"], True),
        ("none_of", ["A", "C"], False),
    ],
)
def test_assignment_matches_non_recovery_source_names(operator, values, expected):
    alert = Alert.objects.create(alert_id="names", fingerprint="names", title="CPU", content="", level="1")
    alert.events.add(make_event("A"), make_event("A"), make_event("B"), make_event("C", "recovery"))
    rules = [[{"key": "source_names", "operator": operator, "value": values}]]
    matcher = MonitorSourceRuleMatcher({}, source_field="push_source_ids")
    assert matcher.filter_queryset(Alert.objects.all(), rules) == ([alert.pk] if expected else [])


@pytest.mark.parametrize(
    "key,actual,wanted", [("level", "1", ["1", "2"]), ("push_source_id", "a", ["a", "b"]), ("source_name", "平台A", ["平台A", "平台B"])]
)
def test_event_scalar_accepts_multiple_exact_candidates(key, actual, wanted):
    from apps.alerts.aggregation.strategy.instant_matcher import InstantMatcher
    from apps.alerts.aggregation.strategy.matcher import StrategyMatcher
    from apps.alerts.enrichment.matcher import event_matches

    event = make_event("平台A")
    event.push_source_id = "a"
    event.save()
    rules = [[{"key": key, "operator": "any_of", "value": wanted}]]
    assert list(StrategyMatcher.match_events_to_strategy(Event.objects.all(), rules)) == [event]
    assert InstantMatcher.match_in_memory(event, rules)
    assert event_matches({key: actual}, rules)
    assert not event_matches({key: actual + "extra"}, rules)


def test_action_source_names_use_fresh_non_recovery_relations():
    from apps.alerts.action.matcher import event_matches
    from apps.alerts.action.payload import build_rule_payload

    alert = Alert.objects.create(alert_id="action", fingerprint="action", title="CPU", content="", level="1")
    alert.events.add(make_event("A"), make_event("B", "recovery"))
    rules = [[{"key": "source_names", "operator": "all_of", "value": ["A", "B"]}]]
    assert not event_matches(build_rule_payload(alert), rules)
    alert.events.add(make_event("B"))
    assert event_matches(build_rule_payload(alert), rules)


def test_list_filter_and_detail_share_names_and_do_not_split_commas(authenticated_user, monkeypatch):
    monkeypatch.setattr("apps.core.utils.serializers.get_permission_rules", lambda *a, **k: {"instance": [], "team": [1]})
    import json

    from apps.alerts.filters.alert import AlertModelFilter
    from apps.alerts.serializers.alert import AlertModelSerializer

    alert = Alert.objects.create(alert_id="detail", fingerprint="detail", title="CPU", content="", level="1")
    alert.events.add(make_event("A,生产"), make_event("B", "recovery"))
    from types import SimpleNamespace

    assert AlertModelSerializer(alert, context={"request": SimpleNamespace(user=authenticated_user, COOKIES={})}).data["source_names"] == ["A,生产"]
    assert list(AlertModelFilter({"source_names": json.dumps(["A,生产"])}, queryset=Alert.objects.all()).qs) == [alert]
    assert not AlertModelFilter({"source_names": '["A","生产","B"]'}, queryset=Alert.objects.all()).qs.exists()


@pytest.mark.parametrize("action", ["recovery", "closed"])
def test_empty_negative_and_closed_event_boundary(action):
    from apps.alerts.action.matcher import event_matches
    from apps.alerts.action.payload import build_rule_payload

    alert = Alert.objects.create(alert_id="empty", fingerprint="empty", title="CPU", content="", level="1")
    alert.events.add(make_event("A", action))
    for operator in ["any_of", "all_of", "none_of"]:
        value = ["B"] if operator == "none_of" else ["A"]
        rules = [[{"key": "source_names", "operator": operator, "value": value}]]
        assert event_matches(build_rule_payload(alert), rules) is (action == "closed")
        actual = MonitorSourceRuleMatcher({}, source_field="push_source_ids").filter_queryset(Alert.objects.all(), rules)
        assert bool(actual) is (action == "closed")


def test_rename_and_soft_delete_follow_associated_name_not_source_options():
    from apps.alerts.action.payload import build_rule_payload

    alert = Alert.objects.create(alert_id="rename", fingerprint="rename", title="CPU", content="", level="1")
    event = make_event("A")
    alert.events.add(event, make_event("A"))
    assert build_rule_payload(alert)["source_names"] == ["A"]
    AlertSource.all_objects.filter(pk=event.source_id).update(name="B", is_delete=True, is_active=False)
    assert build_rule_payload(alert)["source_names"] == ["A", "B"]


def test_source_query_keeps_candidate_scope_and_does_not_duplicate_alerts(django_assert_num_queries):
    from apps.alerts.utils.permission_scope import apply_team_scope_with_group_ids

    visible = Alert.objects.create(alert_id="visible", fingerprint="visible", title="CPU", content="", level="1", team=[1])
    foreign = Alert.objects.create(alert_id="foreign", fingerprint="foreign", title="CPU", content="", level="1", team=[2])
    visible.events.add(make_event("A"), make_event("A"), make_event("B"))
    foreign.events.add(make_event("A"), make_event("B"))
    candidates = apply_team_scope_with_group_ids(Alert.objects.all(), [1])
    rules = [[{"key": "source_names", "operator": "all_of", "value": ["A", "B"]}]]
    with django_assert_num_queries(1):
        assert MonitorSourceRuleMatcher({}, source_field="push_source_ids").filter_queryset(candidates, rules) == [visible.pk]


def test_source_names_are_loaded_once_for_multiple_action_rules(monkeypatch):
    from unittest.mock import Mock

    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from apps.alerts.action.engine import ActionEngine
    from apps.alerts.models.action import ActionExecution, ActionRule

    alert = Alert.objects.create(alert_id="engine", fingerprint="engine", title="CPU", content="", level="1", team=[1])
    alert.events.add(make_event("A"), make_event("B", "recovery"))
    for index in range(3):
        ActionRule.objects.create(
            name=f"rule-{index}",
            scope="alert",
            is_active=True,
            team=[1],
            trigger_events=["created"],
            action_type="job",
            action_config={},
            match_rules=[[{"key": "source_names", "operator": "any_of", "value": ["A", "B"]}]],
        )
    handler = Mock()
    monkeypatch.setattr("apps.alerts.action.engine.get_handler", lambda kind: handler)
    with CaptureQueriesContext(connection) as queries:
        ActionEngine().evaluate(alert, "created")
    assert sum("alerts_alert_events" in q["sql"] and q["sql"].startswith("SELECT") for q in queries) == 1
    assert ActionExecution.objects.filter(alert=alert).count() == 3
    ActionEngine().evaluate(alert, "created")
    assert handler.execute.call_count == 3


def test_severity_validation_uses_scope_specific_catalog():
    from rest_framework.exceptions import ValidationError

    from apps.alerts.models.models import Level
    from apps.alerts.utils.rule_catalog import validate_rules_for_serializer

    Level.objects.create(level_type="event", level_id=1, level_name="one", level_display_name="一")
    Level.objects.create(level_type="event", level_id=2, level_name="two", level_display_name="二")
    Level.objects.create(level_type="alert", level_id=3, level_name="three", level_display_name="三")
    rules = [[{"key": "level", "operator": "any_of", "value": ["1", "2"]}]]
    assert validate_rules_for_serializer(rules, "shield") == rules
    with pytest.raises(ValidationError):
        validate_rules_for_serializer(rules, "assignment")


@pytest.mark.parametrize("invalid", [1, True, "wrong", {"key": "source_names"}, [1]])
def test_invalid_action_does_not_interrupt_later_valid_rule(invalid, monkeypatch):
    from unittest.mock import Mock

    from apps.alerts.action.engine import ActionEngine
    from apps.alerts.models.action import ActionExecution, ActionRule

    alert = Alert.objects.create(alert_id="invalid-action", fingerprint="invalid-action", title="CPU", content="", level="1")
    ActionRule.objects.create(name="bad", scope="alert", is_active=True, trigger_events=["created"], action_type="job", match_rules=invalid)
    valid = ActionRule.objects.create(
        name="good",
        scope="alert",
        is_active=True,
        trigger_events=["created"],
        action_type="job",
        match_rules=[[{"key": "title", "operator": "eq", "value": "CPU"}]],
    )
    handler = Mock()
    monkeypatch.setattr("apps.alerts.action.engine.get_handler", lambda kind: handler)
    ActionEngine().evaluate(alert, "created")
    assert list(ActionExecution.objects.values_list("rule_id", flat=True)) == [valid.pk]
    assert handler.execute.call_count == 1
