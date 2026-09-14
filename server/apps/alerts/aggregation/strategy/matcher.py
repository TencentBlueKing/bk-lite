from apps.alerts.utils.rule_catalog import model_fields, rules_are_valid
from apps.alerts.utils.typed_rules import condition_q, rules_q


class StrategyMatcher:
    FIELD_MAP = model_fields("correlation")

    @staticmethod
    def match_events_to_strategy(events_queryset, match_rules):
        if not rules_are_valid(match_rules, "correlation"):
            return events_queryset.none()
        return events_queryset.filter(rules_q(match_rules, "correlation"))

    @staticmethod
    def _build_q_filter(match_rules):
        return rules_q(match_rules, "correlation")

    @staticmethod
    def _build_condition_q(condition):
        try:
            return condition_q(condition, "correlation")
        except (ValueError, TypeError):
            return None
