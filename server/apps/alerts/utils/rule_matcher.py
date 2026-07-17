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
from typing import Any, Dict, List, Optional

from django.db.models import Q, QuerySet

from apps.core.logger import alert_logger as logger


class RuleMatcher:
    """
    规则匹配器

    用于根据匹配规则构建Django ORM Q对象，并过滤查询集。

    2026-07-17 增强:支持 alt_field_mapping 给单 key 注册 fallback 字段列表，
    主字段匹配不到时仍可通过 fallback 命中（兜历史脏数据 + 防御未来加新 key）。
    """

    def __init__(self, field_mapping: Dict[str, str], alt_field_mapping: Optional[Dict[str, List[str]]] = None):
        """
        初始化规则匹配器

        Args:
            field_mapping: 字段映射字典，键为规则中的key，值为模型字段名
                例如: {"source_id": "source_id", "level_id": "level"}
            alt_field_mapping: 可选，每个 key 对应的 fallback 字段列表。
                命中单条规则时，主字段 OR 上所有 fallback 字段（任一命中即整条命中）。
                例如: {"source_id": ["source_name", "source__source_id"]}
        """
        self.field_mapping = field_mapping
        self.alt_field_mapping = alt_field_mapping or {}

    def filter_queryset(self, queryset: QuerySet, match_rules: List[List[Dict[str, Any]]]) -> List[int]:
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
        invalid_group = False

        for rule in rule_group:
            rule_q = self.build_single_rule_q(rule)
            if rule_q is None:
                invalid_group = True
                logger.warning("[AlertUtil] 规则组因规则失效: %s", rule)
                break

            group_has_valid_rules = True
            if not group_q:
                group_q = rule_q
            else:
                group_q &= rule_q

        if invalid_group:
            return None

        return group_q if group_has_valid_rules else None

    def build_single_rule_q(self, rule: Dict[str, Any]) -> Optional[Q]:
        """
        构建单个规则的Q对象

        2026-07-17 增强:如果 key 在 alt_field_mapping 中注册了 fallback 字段，
        主字段 + fallback 字段的组合语义按操作符区分:
        - 正向操作符(eq/contains/in/re):主 OR alt，任一字段命中即视为命中（兜住 value 写错类型的历史脏数据）
        - 反向操作符(ne/not_contains):主 AND alt，两个字段都不命中才视为命中
          （避免反向操作下"主字段排除 + alt 保留"被错误地解释为"保留"）

        Args:
            rule: 单个匹配规则，包含以下字段：
                - key: 字段键（对应field_mapping中的键）
                - operator: 操作符（eq, ne, contains, not_contains, re）
                - value: 匹配值

        Returns:
            Q对象或None
        """
        key = rule.get("key", "")
        primary_q = self._build_q_for_field(rule, self.field_mapping.get(key), is_primary=True)
        if primary_q is None:
            return None

        alt_fields = self.alt_field_mapping.get(key, [])
        if not alt_fields:
            return primary_q

        operator = rule.get("operator", "eq")
        alt_qs = []
        for alt_field in alt_fields:
            alt_q = self._build_q_for_field(rule, alt_field, is_primary=False)
            if alt_q is not None:
                alt_qs.append(alt_q)

        if not alt_qs:
            return primary_q

        from functools import reduce

        combined_alt = reduce(lambda a, b: a | b, alt_qs)

        # 正向操作符:主 OR alt（任一命中）
        # 反向操作符(ne/not_contains):主 AND alt（都不命中才视为不命中，避免被错误保留）
        if operator in ("ne", "not_contains"):
            return primary_q & combined_alt
        return primary_q | combined_alt

    def _build_q_for_field(self, rule: Dict[str, Any], model_field: Optional[str], is_primary: bool = True) -> Optional[Q]:
        """为单个字段构造 Q 对象（主字段或 fallback 字段共用）。"""
        if not model_field:
            if is_primary:
                logger.warning("[AlertUtil] 未知字段键: %s", rule.get("key", ""))
            return None

        operator = rule.get("operator", "eq")
        value = rule.get("value", "")

        if isinstance(value, list) and not value:
            logger.warning("[AlertUtil] 规则值数组不能为空: %s", rule)
            return None

        try:
            if operator == "eq":
                if isinstance(value, list):
                    return Q(**{f"{model_field}__in": value})
                return Q(**{model_field: value})
            elif operator == "ne":
                if isinstance(value, list):
                    return ~Q(**{f"{model_field}__in": value})
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
                    logger.error("[AlertUtil] 无效的正则表达式 '%s': %s", value, e)
                    return None
                return Q(**{f"{model_field}__iregex": value})
            else:
                if is_primary:
                    logger.warning("[AlertUtil] 未知操作符: %s", operator)
                return None

        except Exception as e:
            logger.error("[AlertUtil] 构建规则 Q 对象失败: %s", e, exc_info=True)
            return None


def filter_by_rules(queryset: QuerySet, match_rules: List[List[Dict[str, Any]]], field_mapping: Dict[str, str]) -> List[int]:
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
