"""多候选值规则的公共语义；旧操作符由原匹配器处理。"""

from django.db.models import Exists, OuterRef, Q

MULTIVALUE_OPERATORS = frozenset({"any_of", "none_of", "all_of", "text_any", "text_all", "text_none"})
MAX_VALUES = 50


def validate_values(operator, values):
    if operator not in MULTIVALUE_OPERATORS:
        raise ValueError("不支持的多值操作符")
    if not isinstance(values, list) or not 1 <= len(values) <= MAX_VALUES:
        raise ValueError("匹配值须为 1 到 50 项的数组")
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (str, int)) or not str(value).strip():
            raise ValueError("匹配值须为非空字符串或整数")
        if len(str(value)) > 256:
            raise ValueError("每个匹配值不能超过 256 个字符")


def matches_values(actual, operator, expected):
    validate_values(operator, expected)
    if operator == "all_of" and not isinstance(actual, list):
        return False
    values = actual if isinstance(actual, list) else [actual]
    values = [str(value) for value in values if isinstance(value, (str, int)) and not isinstance(value, bool) and str(value).strip()]
    if not values:
        return False
    expected = [str(value) for value in expected]
    if operator.startswith("text_"):
        found = [any(needle.casefold() in value.casefold() for value in values) for needle in expected]
    else:
        found = [needle in values for needle in expected]
    if operator in {"none_of", "text_none"}:
        return not any(found)
    return all(found) if operator in {"all_of", "text_all"} else any(found)


def build_multivalue_q(field, operator, expected):
    """标量条件下推 ORM；列表由调用方的有界候选适配处理。"""
    validate_values(operator, expected)
    if field == "events__source_id":
        from apps.alerts.models.models import Alert

        members = Alert.events.through.objects.filter(alert_id=OuterRef("pk"))
        found = Exists(members.filter(event__source_id__in=expected))
        if operator not in {"any_of", "none_of"}:
            raise ValueError("告警源仅支持候选值匹配")
        return Q(Exists(members)) & Q(~found if operator == "none_of" else found)
    exists = Q(**{f"{field}__isnull": False})
    if field not in {"source_id", "events__source_id"}:
        exists &= Q(**{f"{field}__regex": r"\S"})
    if operator in {"any_of", "none_of"}:
        query = Q(**{f"{field}__in": expected})
        return exists & (~query if operator == "none_of" else query)
    if operator == "all_of":
        raise ValueError("包含全部仅适用于列表字段")
    query = None
    for value in expected:
        item = Q(**{f"{field}__icontains": str(value)})
        query = item if query is None else (query & item if operator == "text_all" else query | item)
    return exists & (~query if operator == "text_none" else query)
