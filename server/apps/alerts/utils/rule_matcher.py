# -- coding: utf-8 --
# @File: rule_matcher.py
# @Time: 2025/2/9
# @Author: Refactored from shield.py and assignment.py
"""
通用规则匹配工具

用于构建Django ORM Q对象来过滤匹配规则。
支持的操作符：
- eq: 等于
- ne: 不等于
- contains: 包含
- not_contains: 不包含
- re: 正则表达式匹配
"""

import re as regex_module
from typing import List, Dict, Any, Optional

from django.db.models import Q, QuerySet

from apps.core.logger import alert_logger as logger


class RuleMatcher:
    """
    规则匹配器

    用于根据匹配规则构建Django ORM Q对象，并过滤查询集。
    """

    def __init__(self, field_mapping: Dict[str, str]):
        """
        初始化规则匹配器

        Args:
            field_mapping: 字段映射字典，键为规则中的key，值为模型字段名
                例如: {"source_id": "source__source_id", "level_id": "level"}
        """
        self.field_mapping = field_mapping

    def filter_queryset(
        self,
        queryset: QuerySet,
        match_rules: List[List[Dict[str, Any]]]
    ) -> List[int]:
        """
        使用ORM查询过滤匹配规则

        规则结构说明：
        - 最外层列表是"或"关系
        - 内层列表是"且"关系

        Args:
            queryset: 基础查询集
            match_rules: 匹配规则 [[{},{}],[{},{}]]

        Returns:
            匹配的ID列表
        """
        if not match_rules:
            return list(queryset.values_list("id", flat=True))

        final_q = self._build_combined_q(match_rules)

        if final_q:
            queryset = queryset.filter(final_q)
        else:
            # 如果没有有效的规则，返回空结果集
            queryset = queryset.none()

        return list(queryset.values_list("id", flat=True))

    def _build_combined_q(self, match_rules: List[List[Dict[str, Any]]]) -> Optional[Q]:
        """
        构建组合的Q对象

        Args:
            match_rules: 匹配规则列表

        Returns:
            组合的Q对象或None
        """
        # 最外层是或关系
        final_q = Q()

        for rule_group in match_rules:
            if not rule_group:
                continue

            # 里层是且关系
            group_q = self._build_group_q(rule_group)

            # 只有当组内有有效规则时才添加到最终查询
            if group_q:
                if not final_q:
                    final_q = group_q
                else:
                    final_q |= group_q

        return final_q if final_q else None

    def _build_group_q(self, rule_group: List[Dict[str, Any]]) -> Optional[Q]:
        """
        构建规则组的Q对象（组内为"且"关系）

        Args:
            rule_group: 规则组

        Returns:
            组合的Q对象或None
        """
        group_q = Q()
        group_has_valid_rules = False

        for rule in rule_group:
            rule_q = self.build_single_rule_q(rule)
            if rule_q:
                group_has_valid_rules = True
                if not group_q:
                    group_q = rule_q
                else:
                    group_q &= rule_q

        return group_q if group_has_valid_rules else None

    def build_single_rule_q(self, rule: Dict[str, Any]) -> Optional[Q]:
        """
        构建单个规则的Q对象

        Args:
            rule: 单个匹配规则，包含以下字段：
                - key: 字段键（对应field_mapping中的键）
                - operator: 操作符（eq, ne, contains, not_contains, re）
                - value: 匹配值

        Returns:
            Q对象或None
        """
        key = rule.get("key", "")
        operator = rule.get("operator", "eq")
        value = rule.get("value", "")
        model_field = self.field_mapping.get(key)

        if not model_field:
            logger.warning(f"Unknown field key: {key}")
            return None

        try:
            if operator == "eq":
                return Q(**{model_field: value})
            elif operator == "ne":
                return ~Q(**{model_field: value})
            elif operator == "contains":
                return Q(**{f"{model_field}__icontains": value})
            elif operator == "not_contains":
                return ~Q(**{f"{model_field}__icontains": value})
            elif operator == "re":
                # 验证正则表达式有效性
                try:
                    regex_module.compile(value)
                except regex_module.error as e:
                    logger.error(f"Invalid regex pattern '{value}': {e}")
                    return None
                return Q(**{f"{model_field}__iregex": value})
            else:
                logger.warning(f"Unknown operator: {operator}")
                return None

        except Exception as e:
            logger.error(f"Error building Q object for rule: {str(e)}")
            return None


def filter_by_rules(
    queryset: QuerySet,
    match_rules: List[List[Dict[str, Any]]],
    field_mapping: Dict[str, str]
) -> List[int]:
    """
    根据规则过滤查询集

    便捷函数，用于快速调用规则过滤。

    Args:
        queryset: 基础查询集
        match_rules: 匹配规则
        field_mapping: 字段映射

    Returns:
        匹配的ID列表
    """
    matcher = RuleMatcher(field_mapping)
    return matcher.filter_queryset(queryset, match_rules)
