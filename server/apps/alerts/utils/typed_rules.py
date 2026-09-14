"""当前模型的严格规则执行；ORM 与内存共享字段和值契约。"""

import math
import re
from functools import reduce
from operator import and_, or_

from django.db.models import Q

from apps.alerts.utils.rule_catalog import rules_are_valid, validate_condition


def matches_condition(actual, condition, spec):
    operator, expected = condition["operator"], condition["value"]
    if spec["type"] == "list":
        if not isinstance(actual, list) or not actual or any(not isinstance(item, str) for item in actual):
            return False
        values = {item for item in actual if item.strip()}
        if not values:
            return False
        wanted = set(expected)
        return {"any_of": bool(values & wanted), "all_of": wanted <= values, "none_of": not values & wanted}[operator]
    if spec["type"] == "str":
        if not isinstance(actual, str) or not actual.strip():
            return False
    elif (
        isinstance(actual, bool)
        or not isinstance(actual, int if spec["type"] == "int" else (int, float))
        or (isinstance(actual, float) and not math.isfinite(actual))
    ):
        return False
    if operator == "eq":
        return actual == expected
    if operator == "ne":
        return actual != expected
    if operator == "any_of":
        return actual in expected
    if operator == "none_of":
        return actual not in expected
    if operator in {"gt", "gte", "lt", "lte"}:
        return {"gt": actual > expected, "gte": actual >= expected, "lt": actual < expected, "lte": actual <= expected}[operator]
    if operator == "contains":
        return expected.lower() in actual.lower()
    if operator == "not_contains":
        return expected.lower() not in actual.lower()
    if operator == "re":
        return re.search(expected, actual, re.IGNORECASE) is not None
    return False


def matches_payload(payload, rules, scope):
    if not rules_are_valid(rules, scope):
        return False
    return not rules or any(
        all(matches_condition(payload.get(rule["key"]), rule, validate_condition(rule, scope)) for rule in group) for group in rules
    )


def condition_q(condition, scope):
    spec = validate_condition(condition, scope)
    field, operator, value = spec["orm"], condition["operator"], condition["value"]
    if spec.get("resolver") == "alert_sources":
        from apps.alerts.service.source_names import source_names_q

        return source_names_q(operator, value)
    if spec["type"] == "list":
        raise ValueError("列表字段须在有界候选集中匹配")
    present = Q(**{f"{field}__isnull": False})
    if spec["type"] == "str":
        present &= ~Q(**{f"{field}__regex": r"^\s*$"})
    lookup = {
        "eq": "exact",
        "ne": "exact",
        "any_of": "in",
        "none_of": "in",
        "contains": "icontains",
        "not_contains": "icontains",
        "re": "iregex",
        "gt": "gt",
        "gte": "gte",
        "lt": "lt",
        "lte": "lte",
    }[operator]
    predicate = Q(**{f"{field}__{lookup}": value})
    return present & (~predicate if operator in {"ne", "not_contains", "none_of"} else predicate)


def rules_q(rules, scope, build=None):
    if not rules_are_valid(rules, scope):
        return Q(pk__in=[])
    build = build or (lambda rule: condition_q(rule, scope))
    return reduce(or_, (reduce(and_, (build(rule) for rule in group)) for group in rules), Q(pk__in=[])) if rules else Q()
