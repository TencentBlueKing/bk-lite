"""按模型类型限制规则的公共接口回归。"""

import pytest

from apps.alerts.serializers.action import ActionRuleSerializer
from apps.alerts.serializers.assignment_shield import AlertAssignmentModelSerializer, AlertShieldModelSerializer
from apps.alerts.serializers.enrichment import EnrichmentRuleModelSerializer
from apps.alerts.serializers.strategy import AlarmStrategySerializer

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

SERIALIZERS = [
    AlarmStrategySerializer,
    AlertShieldModelSerializer,
    EnrichmentRuleModelSerializer,
    AlertAssignmentModelSerializer,
    ActionRuleSerializer,
]


@pytest.mark.parametrize("serializer", SERIALIZERS)
def test_text_does_not_accept_set_membership(serializer):
    form = serializer(
        data={
            "name": "typed",
            "strategy_type": "smart_denoise",
            "input_binding": {"model_id": "resource_type", "inst_uuid": "resource_id"},
            "match_rules": [[{"key": "title", "operator": "any_of", "value": ["a", "b"]}]],
        },
        partial=True,
    )
    assert not form.is_valid()
    assert "match_rules" in form.errors


@pytest.mark.parametrize(
    "bad",
    [
        {"key": "title", "operator": "any_of", "value": ["CPU"]},
        {"key": "source_pk", "operator": "eq", "value": 1},
        {"key": "level_id", "operator": "eq", "value": "1"},
    ],
)
def test_invalid_saved_condition_fails_the_entire_rule_in_all_event_engines(bad):
    from django.utils import timezone

    from apps.alerts.aggregation.strategy.instant_matcher import InstantMatcher
    from apps.alerts.aggregation.strategy.matcher import StrategyMatcher
    from apps.alerts.common.shield import EventShieldOperator
    from apps.alerts.enrichment.matcher import event_matches
    from apps.alerts.models import AlertSource, Event
    from apps.alerts.utils.monitor_source_rules import MonitorSourceRuleMatcher

    source = AlertSource.objects.create(name="test", source_id="business-code", source_type="restful", secret="test")
    event = Event.objects.create(source=source, event_id="typed-event", title="CPU", level="1", start_time=timezone.now(), raw_data={})
    rules = [[bad], [{"key": "title", "operator": "eq", "value": "CPU"}]]
    assert not StrategyMatcher.match_events_to_strategy(Event.objects.all(), rules).exists()
    assert not InstantMatcher.match_in_memory(event, rules)
    assert not MonitorSourceRuleMatcher(EventShieldOperator.FIELD_MAPPING, source_field="push_source_id").filter_queryset(Event.objects.all(), rules)
    assert not event_matches({"title": "CPU", "level": "1"}, rules)


@pytest.mark.parametrize("source_field", ["push_source_id", "push_source_ids"])
def test_filter_mode_with_empty_conditions_does_not_widen_to_all(source_field):
    from apps.alerts.models import Alert
    from apps.alerts.utils.monitor_source_rules import MonitorSourceRuleMatcher

    Alert.objects.create(alert_id="empty-filter", fingerprint="empty-filter", title="CPU", content="", level="1")
    assert MonitorSourceRuleMatcher({}, source_field=source_field).filter_queryset(Alert.objects.all(), []) == []
