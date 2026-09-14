"""当前 Event/Alert 模型的规则字段、操作符与值类型契约。"""

import json
import math
import re
from pathlib import Path

FIELDS = {field["key"]: field for field in json.loads(Path(__file__).with_name("rule_fields.json").read_text())}
EVENT_SCOPES = {"correlation", "shield", "enrichment"}
SCOPES = EVENT_SCOPES | {"assignment", "action"}


def field_spec(key, scope):
    if scope not in SCOPES:
        raise ValueError("无效的规则场景")
    field = FIELDS.get(key)
    if field and ("event" if scope in EVENT_SCOPES else "alert") in field["contexts"]:
        return field
    raise ValueError("字段不适用于当前规则，请重新配置")


def validate_condition(rule, scope):
    if not isinstance(rule, dict) or not isinstance(rule.get("key"), str):
        raise ValueError("匹配条件格式无效")
    spec = field_spec(rule["key"], scope)
    operator, value = rule.get("operator"), rule.get("value")
    if operator not in spec["operators"]:
        raise ValueError("操作符不适用于该字段类型，请重新配置")
    kind = spec["type"]
    if operator in {"any_of", "all_of", "none_of"}:
        if not isinstance(value, list) or not 1 <= len(value) <= 50:
            raise ValueError("列表匹配值须为 1 到 50 项的数组")
        values = value
        kind = spec.get("item_type", kind)
    else:
        values = [value]
    for item in values:
        if kind == "str":
            if not isinstance(item, str) or not item.strip() or len(item) > spec["max_length"]:
                raise ValueError("匹配值须为非空字符串，且不能超过 256 个字符")
        elif kind in {"int", "float"}:
            if (
                isinstance(item, bool)
                or not isinstance(item, int if kind == "int" else (int, float))
                or (isinstance(item, float) and not math.isfinite(item))
            ):
                raise ValueError("匹配值须为有效数字")
            if spec["role"] == "reference" and not 0 < item <= 9007199254740991:
                raise ValueError("告警源须选择有效 ID")
    if operator == "re":
        try:
            re.compile(value)
        except re.error as error:
            raise ValueError("正则表达式无效") from error
    return spec


def validate_rules(rules, scope):
    if not isinstance(rules, list) or len(rules) > 20:
        raise ValueError("条件组须为数组，最多 20 组")
    count = 0
    for group in rules:
        if not isinstance(group, list) or not group:
            raise ValueError("条件组不能为空")
        count += len(group)
        if count > 100:
            raise ValueError("匹配条件最多 100 条")
        for rule in group:
            validate_condition(rule, scope)
    return rules


def rules_are_valid(rules, scope):
    try:
        validate_rules(rules, scope)
        return True
    except (ValueError, TypeError):
        return False


def validate_rules_for_serializer(rules, scope):
    from rest_framework.exceptions import ValidationError

    try:
        validate_rules(rules, scope)
        level_values = {value for group in rules for rule in group if rule["key"] == "level" for value in rule["value"]}
        if level_values:
            from apps.alerts.models.models import Level

            level_type = "event" if scope in EVENT_SCOPES else "alert"
            allowed = {str(value) for value in Level.objects.filter(level_type=level_type).values_list("level_id", flat=True)}
            if not level_values <= allowed:
                raise ValueError("请选择当前场景的有效级别")
        return rules
    except (ValueError, TypeError) as error:
        raise ValidationError(str(error)) from error


def model_fields(scope):
    return {key: field["orm"] for key, field in FIELDS.items() if ("event" if scope in EVENT_SCOPES else "alert") in field["contexts"]}
