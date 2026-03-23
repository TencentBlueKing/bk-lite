import re
from typing import List, Dict, Any
from django.db.models import Q
from apps.core.logger import alert_logger as logger


class StrategyMatcher:
    OPERATOR_MAP = {
        "eq": "exact",
        "等于": "exact",
        "ne": "ne",
        "不等于": "ne",
        "contains": "icontains",
        "包含": "icontains",
        "not_contains": "not_contains",
        "不包含": "not_contains",
        "正则": "iregex",
        "re": "iregex",
        "regex": "iregex",
        "gt": "gt",
        "大于": "gt",
        "gte": "gte",
        "大于等于": "gte",
        "lt": "lt",
        "小于": "lt",
        "lte": "lte",
        "小于等于": "lte",
        "in": "in",
        "字中串": "in",
        "not_in": "not_in",
    }

    FIELD_MAP = {
        "标题": "title",
        "title": "title",
        "告警源": "source__name",
        "source": "source__name",
        "级别": "level",
        "level": "level",
        "类型对象": "resource_type",
        "resource_type": "resource_type",
        "对象实例": "resource_name",
        "resource_name": "resource_name",
        "内容": "description",
        "description": "description",
        "告警类型": "event_type",
        "event_type": "event_type",
        "服务": "service",
        "service": "service",
        "位置": "location",
        "location": "location",
        "事件ID": "event_id",
        "event_id": "event_id",
        "资源ID": "resource_id",
        "resource_id": "resource_id",
        "指标": "item",
        "item": "item",
    }

    @staticmethod
    def match_events_to_strategy(events_queryset, match_rules: List[List[Dict]]):
        """
        基于AlarmStrategy.match_rules使用ORM过滤事件

        match_rules结构:
        [
            [  # OR 组1 (这组内的条件是 AND 关系)
                {"key": "title", "operator": "eq", "value": "test"},
                {"key": "level", "operator": "eq", "value": 2}
            ],
            [  # OR 组2 (这组内的条件是 AND 关系)
                {"key": "source", "operator": "contains", "value": "cpu"}
            ]
        ]
        最终逻辑: (组1的AND条件) OR (组2的AND条件)
        """
        if not match_rules:
            logger.debug("无match_rules，返回全部事件")
            return events_queryset

        try:
            q_filter = StrategyMatcher._build_q_filter(match_rules)

            logger.debug(
                f"match_rules过滤: {len(match_rules)}组条件, "
                f"首组示例: {match_rules[0][:2] if match_rules and match_rules[0] else 'empty'}"
            )

            filtered_events = events_queryset.filter(q_filter)

            return filtered_events

        except Exception as e:  # noqa
            logger.exception("match_rules过滤失败")
            return events_queryset.none()

    @staticmethod
    def _build_q_filter(match_rules: List[List[Dict]]) -> Q:
        """
        构建Django Q对象

        外层列表: OR 关系
        内层列表: AND 关系

        Returns:
            Q对象，如果所有条件都无效则返回空Q()（匹配所有）
        """
        or_conditions = []

        for and_group in match_rules:
            if not and_group:
                continue

            and_conditions = []

            for condition in and_group:
                q_obj = StrategyMatcher._build_condition_q(condition)
                # 只有当q_obj不为None时才添加（跳过无效条件）
                if q_obj is not None:
                    and_conditions.append(q_obj)

            # 如果该AND组至少有一个有效条件，才构建Q对象
            if and_conditions:
                # 将列表中的Q对象用AND连接
                combined_and = and_conditions[0]
                for q in and_conditions[1:]:
                    combined_and &= q
                or_conditions.append(combined_and)

        # 如果没有任何有效的OR条件组，返回空Q()（匹配所有记录）
        if not or_conditions:
            logger.warning("所有match_rules条件都无效，返回空过滤器")
            return Q()

        # 将多个OR条件组合并
        final_q = or_conditions[0]
        for q in or_conditions[1:]:
            final_q |= q

        return final_q

    @staticmethod
    def _build_condition_q(condition: Dict) -> Q | None:
        """
        将单个条件转换为Q对象

        condition格式:
        {
            "key": "title",        # 字段名（支持中文或英文）
            "operator": "eq",      # 操作符（支持中文或英文）
            "value": "test"        # 值
        }

        Returns:
            Q对象，如果条件无效返回None（而非空Q对象，以便调用方可以跳过该条件）
        """
        key = condition.get("key")
        operator = condition.get("operator")
        value = condition.get("value")

        # 验证必填字段
        if not key or operator is None:
            logger.warning(f"无效条件（缺少key或operator）: {condition}")
            return None

        # value为None时，只有特定操作符才合法
        if value is None and operator not in ["ne", "不等于"]:
            logger.warning(f"无效条件（value为None但operator不支持）: {condition}")
            return None

        field_name = StrategyMatcher.FIELD_MAP.get(key, key)
        django_operator = StrategyMatcher.OPERATOR_MAP.get(operator, "exact")

        # 处理取反操作符
        if django_operator == "not_contains":
            if value is None or value == "":
                logger.warning(f"not_contains操作符的value不能为空: {condition}")
                return None
            return ~Q(**{f"{field_name}__icontains": value})
        elif django_operator == "ne":
            return ~Q(**{f"{field_name}__exact": value})
        elif django_operator == "not_in":
            if not isinstance(value, (list, tuple)):
                logger.warning(f"not_in操作符需要列表类型的value: {condition}")
                return None
            return ~Q(**{f"{field_name}__in": value})

        # 处理正则表达式
        elif django_operator == "iregex":
            if not value:
                logger.warning(f"正则表达式不能为空: {condition}")
                return None
            # 验证正则表达式语法（注意：PostgreSQL使用POSIX正则，可能与Python re模块略有差异）
            try:
                re.compile(value)
            except re.error as e:
                logger.error(f"无效的正则表达式 '{value}': {e}")
                # 返回None让调用方跳过该条件，而非返回空结果集
                return None
            # PostgreSQL使用 ~* 操作符进行不区分大小写的正则匹配
            return Q(**{f"{field_name}__iregex": value})

        # 处理in操作符
        elif django_operator == "in":
            if not isinstance(value, (list, tuple)):
                logger.warning(f"in操作符需要列表类型的value: {condition}")
                return None
            return Q(**{f"{field_name}__in": value})

        # 处理其他标准操作符
        else:
            return Q(**{f"{field_name}__{django_operator}": value})

    @staticmethod
    def _event_to_dict(event) -> Dict[str, Any]:
        """事件转字典（保留用于向后兼容）"""
        result = {
            "event_id": event.event_id,
            "title": event.title,
            "description": event.description,
            "level": event.level,
            "resource_name": event.resource_name,
            "resource_id": event.resource_id,
            "resource_type": event.resource_type,
            "item": event.item,
            "external_id": event.external_id,
            "action": event.action,
            "source_id": event.source_id,
            "rule_id": event.rule_id,
            "service": event.service,
            "location": event.location,
            "event_type": event.event_type,
        }
        if event.labels:
            result.update(event.labels)
        if event.tags:
            result.update(event.tags)
        return result
