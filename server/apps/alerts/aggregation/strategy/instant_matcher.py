"""即时告警旁路用的内存匹配器。

语义与 ``StrategyMatcher`` 完全一致（同样的 OPERATOR_MAP / FIELD_MAP 与 OR/AND 嵌套），
区别仅在于：作用于 Python 对象属性而非 Django ORM Q 表达式，零 DB 查询。

任何与 ``StrategyMatcher`` 的语义分歧都视为 bug。
"""

import re
from typing import Any, Dict, List, Optional

from apps.alerts.aggregation.strategy.matcher import StrategyMatcher
from apps.alerts.models.models import Event
from apps.core.logger import alert_logger as logger


class InstantMatcher:
    OPERATOR_MAP = StrategyMatcher.OPERATOR_MAP
    FIELD_MAP = StrategyMatcher.FIELD_MAP

    @staticmethod
    def match_in_memory(event: Event, match_rules: Optional[List[List[Dict[str, Any]]]]) -> bool:
        """单 event × 单策略 match_rules 命中判断。

        - 外层 OR、内层 AND，与 StrategyMatcher 完全一致
        - 空 / 非法 match_rules 一律视为不命中（不做无差别命中，避免误触）
        """
        if not match_rules:
            return False

        try:
            for and_group in match_rules:
                if not and_group:
                    continue
                if all(InstantMatcher._eval_condition(event, cond) for cond in and_group):
                    return True
        except Exception:
            logger.exception("instant matcher 评估异常，视为不命中")
            return False
        return False

    @staticmethod
    def _eval_condition(event: Event, condition: Dict[str, Any]) -> bool:
        key = condition.get("key")
        operator = condition.get("operator")
        value = condition.get("value")

        if not key or operator is None:
            return False

        django_op = InstantMatcher.OPERATOR_MAP.get(operator)
        if django_op is None:
            return False

        field_name = InstantMatcher.FIELD_MAP.get(key, key)
        event_value = InstantMatcher._get_field_value(event, field_name)

        # value 为 None：与 StrategyMatcher 一致，仅 ne/不等于 合法
        if value is None and django_op != "ne":
            return False

        if django_op == "exact":
            return InstantMatcher._equal(event_value, value)
        if django_op == "ne":
            return not InstantMatcher._equal(event_value, value)
        if django_op == "icontains":
            return InstantMatcher._icontains(event_value, value)
        if django_op == "not_contains":
            if value in (None, ""):
                return False
            return not InstantMatcher._icontains(event_value, value)
        if django_op == "iregex":
            if not value:
                return False
            try:
                pattern = re.compile(str(value), re.IGNORECASE)
            except re.error:
                return False
            return bool(pattern.search(InstantMatcher._to_str(event_value)))
        if django_op == "in":
            if not isinstance(value, (list, tuple)):
                return False
            return any(InstantMatcher._equal(event_value, v) for v in value)
        if django_op == "not_in":
            if not isinstance(value, (list, tuple)):
                return False
            return not any(InstantMatcher._equal(event_value, v) for v in value)
        if django_op in {"gt", "gte", "lt", "lte"}:
            return InstantMatcher._numeric_compare(event_value, value, django_op)
        return False

    @staticmethod
    def _get_field_value(event: Event, field_name: str) -> Any:
        """字段取值。

        - source__name 走 event.source.name
        - 其他字段：先取 event 属性；缺失再回退到 event.labels / event.tags
        """
        if field_name == "source__name":
            source = getattr(event, "source", None)
            return getattr(source, "name", None) if source else None

        if hasattr(event, field_name):
            return getattr(event, field_name)

        labels = getattr(event, "labels", None) or {}
        if field_name in labels:
            return labels[field_name]

        tags = getattr(event, "tags", None) or {}
        if field_name in tags:
            return tags[field_name]

        return None

    @staticmethod
    def _to_str(value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    @staticmethod
    def _equal(left: Any, right: Any) -> bool:
        if left is None and right is None:
            return True
        if left is None or right is None:
            return False
        # 数值与字符串混用时按字符串比较，复合现有 ORM exact 语义
        return InstantMatcher._to_str(left) == InstantMatcher._to_str(right)

    @staticmethod
    def _icontains(haystack: Any, needle: Any) -> bool:
        if needle in (None, ""):
            return False
        return str(needle).lower() in InstantMatcher._to_str(haystack).lower()

    @staticmethod
    def _numeric_compare(left: Any, right: Any, op: str) -> bool:
        try:
            l, r = float(left), float(right)
        except (TypeError, ValueError):
            return False
        if op == "gt":
            return l > r
        if op == "gte":
            return l >= r
        if op == "lt":
            return l < r
        if op == "lte":
            return l <= r
        return False
