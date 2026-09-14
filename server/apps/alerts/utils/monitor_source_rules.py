"""分派、屏蔽的严格规则匹配；Alert JSON 列表在有界候选集中执行。"""
from django.db.models import Q

from apps.alerts.utils.rule_catalog import rules_are_valid, validate_condition
from apps.alerts.utils.typed_rules import condition_q, matches_condition, rules_q


def compile_monitor_source_rule(rule):
    scope = "assignment" if rule.get("key") == "push_source_ids" else "shield"
    spec = validate_condition(rule, scope)
    return lambda actual: matches_condition(actual, rule, spec)


class MonitorSourceRuleMatcher:
    BATCH_SIZE = 200

    def __init__(self, field_mapping, *, source_field):
        self.field_mapping = field_mapping
        self.source_field = source_field
        self.scope = "assignment" if source_field == "push_source_ids" else "shield"
        self._source_values = {}

    def filter_queryset(self, queryset, match_rules):
        if not match_rules or not rules_are_valid(match_rules, self.scope):
            return []
        has_list = self.scope == "assignment" and any(rule["key"] == "push_source_ids" for group in match_rules for rule in group)
        if not has_list:
            return list(queryset.filter(rules_q(match_rules, self.scope)).values_list("pk", flat=True).distinct())
        matched_ids, last_pk = [], 0
        try:
            while True:
                ids = list(queryset.filter(pk__gt=last_pk).order_by("pk").values_list("pk", flat=True).distinct()[: self.BATCH_SIZE])
                if not ids:
                    break
                self._source_values = dict(queryset.model.objects.using(queryset.db).filter(pk__in=ids).values_list("pk", self.source_field))
                matched_ids.extend(
                    queryset.filter(pk__in=ids)
                    .filter(rules_q(match_rules, self.scope, self.build_single_rule_q))
                    .values_list("pk", flat=True)
                    .distinct()
                )
                last_pk = ids[-1]
        finally:
            self._source_values = {}
        return list(dict.fromkeys(matched_ids))

    def build_single_rule_q(self, rule):
        if self.scope == "assignment" and rule["key"] == "push_source_ids":
            matches = compile_monitor_source_rule(rule)
            return Q(pk__in=[pk for pk, values in self._source_values.items() if matches(values)])
        return condition_q(rule, self.scope)
