# -- coding: utf-8 --
# @File: shield.py
# @Time: 2025/6/16 15:35
# @Author: windyzhao
"""
# Shield class for handling event shielding operations.
"""

import datetime
from typing import List, Dict, Any
from django.db.models import Q
from django.utils import timezone
from django.db import transaction

from apps.alerts.error import ShieldNotFoundError, EventNotFoundError
from apps.alerts.models import AlertShield, Event
from apps.alerts.constants import AlertShieldMatchType, EventStatus
from apps.core.logger import alert_logger as logger


class EventShieldOperator(object):
    """
    事件屏蔽
    符合条件的事件和在规定时间内产生的事件将被屏蔽，屏蔽后不会触发通知或其他处理流程。
    """

    def __init__(self, event_id_list: List[str], active_shields=None):
        """
        初始化事件屏蔽操作器（性能优化版）
        
        Args:
            event_id_list: 事件ID列表
            active_shields: 预加载的活跃屏蔽策略（可选，避免重复查询）
        """
        # 优化：支持传入预加载的屏蔽策略
        if active_shields is not None:
            self.active_shields = active_shields
        else:
            self.active_shields = self.get_shields()
        
        if not self.active_shields:
            raise ShieldNotFoundError()
        
        self.event_received_at = None
        self.event_id_list = event_id_list
        self.events = self.get_event_map()
        if not self.events:
            raise EventNotFoundError()
        # 字段映射到模型字段
        self.field_mapping = {
            "source_id": "source__source_id",
            "level_id": "level",
            "resource_type": "resource_type",
            "resource_id": "resource_id",
            "content": "description",
            "title": "title",
            "event_id": "event_id",
        }

    def get_event_map(self) -> Dict[int, Event]:
        """获取事件实例映射"""
        result = {}
        events = Event.objects.filter(event_id__in=self.event_id_list)
        self.event_received_at = events[0].received_at if events else timezone.now()
        for event in events:
            result[event.id] = event
        return result

    @staticmethod
    def get_shields():
        """获取活跃的屏蔽策略"""
        instances = AlertShield.objects.filter(is_active=True)
        return instances

    def execute_shield_check(self) -> Dict[str, Any]:
        """
        执行屏蔽检查主流程

        Returns:
            Dict[str, Any]: 执行结果统计
        """
        if not self.events:
            logger.warning("No events found for shield check")
            return {
                "total_events": 0,
                "shielded_events": 0,
                "unshielded_events": 0,
                "shield_results": [],
            }

        # 获取所有活跃的屏蔽策略，并预先过滤时间范围
        self.active_shields = self._get_time_matched_shields()

        results = {
            "total_events": len(self.events),
            "shielded_events": 0,
            "unshielded_events": 0,
            "shield_results": [],
        }

        # 记录已屏蔽的事件ID
        shielded_event_ids = set()

        # 按屏蔽策略批量处理事件
        for shield in self.active_shields:
            try:
                # 批量查找匹配该屏蔽策略的事件（排除已屏蔽的）
                matched_event_ids = self._batch_find_matching_events(
                    shield, shielded_event_ids
                )

                if not matched_event_ids:
                    continue

                # 批量执行屏蔽操作
                shield_results = self._batch_execute_shield(matched_event_ids, shield)
                results["shield_results"].extend(shield_results)

                # 统计结果并记录已屏蔽的事件
                for result in shield_results:
                    if result["success"]:
                        results["shielded_events"] += 1
                        shielded_event_ids.add(result["event_id"])

            except Exception as e:
                logger.error(f"Error processing shield {shield.id}: {str(e)}")
                continue

        results["unshielded_events"] = (
            results["total_events"] - results["shielded_events"]
        )
        logger.info(f"Shield check completed: {results}")
        return results

    def _get_time_matched_shields(self) -> List[AlertShield]:
        """
        获取时间范围匹配的屏蔽策略列表

        Returns:
            时间范围内的屏蔽策略列表
        """

        time_matched_shields = []
        for shield in self.active_shields:
            if self._check_time_range(shield.suppression_time):
                time_matched_shields.append(shield)
            else:
                logger.debug(f"Shield {shield.id} time range not matched, skipping")

        return time_matched_shields

    def _batch_find_matching_events(
        self, shield: AlertShield, excluded_ids: set = None
    ) -> List[int]:
        """
        批量查找匹配指定屏蔽策略的事件ID列表

        Args:
            shield: 屏蔽策略
            excluded_ids: 需要排除的事件ID集合

        Returns:
            匹配的事件ID列表
        """
        # 先过滤活跃状态的事件（未关闭且未屏蔽的事件才需要屏蔽）
        base_queryset = Event.objects.filter(
            event_id__in=self.event_id_list,
            status=EventStatus.PENDING,  # 只屏蔽开放和已确认的事件
        )

        # 排除已屏蔽的事件
        if excluded_ids:
            base_queryset = base_queryset.exclude(id__in=excluded_ids)

        if shield.match_type == AlertShieldMatchType.ALL:
            # 全部匹配，返回所有活跃的事件
            return list(base_queryset.values_list("id", flat=True))

        elif shield.match_type == AlertShieldMatchType.FILTER:
            # 过滤匹配，使用ORM查询
            return self._orm_filter_events(base_queryset, shield.match_rules or [])

        return []

    def _orm_filter_events(
        self, queryset, match_rules: List[List[Dict[str, Any]]]
    ) -> List[int]:
        """
        使用ORM查询过滤匹配规则的事件

        Args:
            queryset: 基础查询集
            match_rules: 匹配规则 [[{},{}],[{},{}]]

        Returns:
            匹配的事件ID列表
        """
        if not match_rules:
            return list(queryset.values_list("id", flat=True))

        # 最外层是或关系
        final_q = Q()

        for rule_group in match_rules:
            if not rule_group:
                continue

            # 里层是且关系
            group_q = Q()
            group_has_valid_rules = False

            for rule in rule_group:
                rule_q = self._build_single_rule_q(rule)
                if rule_q:
                    group_has_valid_rules = True
                    if not group_q:
                        group_q = rule_q
                    else:
                        group_q &= rule_q

            # 只有当组内有有效规则时才添加到最终查询
            if group_has_valid_rules and group_q:
                if not final_q:
                    final_q = group_q
                else:
                    final_q |= group_q

        if final_q:
            queryset = queryset.filter(final_q)
        else:
            # 如果没有有效的规则，返回空结果集
            queryset = queryset.none()

        return list(queryset.values_list("id", flat=True))

    def _build_single_rule_q(self, rule: Dict[str, Any]) -> Q | None:
        """
        构建单个规则的Q对象
        Args:
            rule: 单个匹配规则
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
                try:
                    import re as regex_module

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

    def _batch_execute_shield(
        self, event_ids: List[int], shield: AlertShield
    ) -> List[Dict[str, Any]]:
        """
        批量执行事件屏蔽操作

        Args:
            event_ids: 事件ID列表
            shield: 屏蔽策略

        Returns:
            屏蔽结果列表
        """
        results = []

        try:
            with transaction.atomic():
                # 先获取要屏蔽的事件信息，用于记录结果
                events_to_shield = Event.objects.filter(
                    id__in=event_ids, status=EventStatus.PENDING
                ).values("id", "event_id")

                # 批量更新事件状态
                updated_count = Event.objects.filter(
                    id__in=event_ids, status=EventStatus.PENDING
                ).update(status=EventStatus.SHIELD)

                # 为每个成功屏蔽的事件记录结果
                for event_info in events_to_shield:
                    logger.debug(
                        f"Event {event_info['event_id']} shielded successfully by shield policy {shield.id}"
                    )

                    results.append(
                        {
                            "event_id": event_info["id"],
                            "success": True,
                            "shield_id": shield.id,
                            "shield_name": shield.name,
                        }
                    )

                logger.info(
                    f"Batch shield completed: {updated_count} events shielded by policy {shield.id}"
                )

        except Exception as e:
            logger.error(f"Error in batch shield: {str(e)}")
            # 如果批量操作失败，为所有事件添加失败记录
            for event_id in event_ids:
                results.append(
                    {
                        "event_id": event_id,
                        "success": False,
                        "message": str(e),
                        "shield_id": shield.id,
                    }
                )

        return results

    def _check_time_range(self, suppression_time: Dict[str, Any]) -> bool:
        """
        检查当前时间是否在配置的屏蔽时间范围内

        Args:
            suppression_time: 屏蔽时间配置

        Returns:
            bool: 是否在屏蔽时间范围内
        """
        if not suppression_time:
            return True

        time_type = suppression_time.get("type", "one")
        # current_time = timezone.now()
        current_time = self.event_received_at  # 使用事件接收时间作为当前时间

        try:
            if time_type == "one":
                # 一次性时间范围
                start_time_str = suppression_time.get("start_time")
                end_time_str = suppression_time.get("end_time")

                # 如果没有配置时间范围，则不符合条件
                if not start_time_str or not end_time_str:
                    logger.warning(
                        "One-time shield range missing start_time or end_time"
                    )
                    return False

                start_time = datetime.datetime.strptime(
                    start_time_str, "%Y-%m-%d %H:%M:%S"
                )
                end_time = datetime.datetime.strptime(end_time_str, "%Y-%m-%d %H:%M:%S")

                # 转换为带时区的时间
                start_time = timezone.make_aware(start_time)
                end_time = timezone.make_aware(end_time)

                return start_time <= current_time <= end_time

            elif time_type == "day":
                # 每日时间范围
                start_time_str = suppression_time.get("start_time")
                end_time_str = suppression_time.get("end_time")

                # 如果没有配置时间范围，则不符合条件
                if not start_time_str or not end_time_str:
                    logger.warning(
                        "Day-time shield range missing start_time or end_time"
                    )
                    return False

                current_time_str = current_time.strftime("%H:%M:%S")
                return start_time_str <= current_time_str <= end_time_str

            elif time_type == "week":
                # 每周时间范围：先检查是否是指定的周几，再检查时间范围
                week_day = suppression_time.get("week_month")
                current_weekday = str(current_time.weekday() + 1)  # Monday is 1

                # 如果不是指定的周几，直接返回False
                if int(current_weekday) not in week_day:
                    return False

                # 检查时间范围
                start_time_str = suppression_time.get("start_time")
                end_time_str = suppression_time.get("end_time")

                # 如果没有配置时间范围，则只要周几匹配就符合条件
                if not start_time_str or not end_time_str:
                    return True

                # 只比较时间部分（HH:MM:SS）
                if len(start_time_str) > 8:  # 包含日期的格式
                    start_time_str = (
                        start_time_str.split(" ")[1]
                        if " " in start_time_str
                        else start_time_str[-8:]
                    )
                if len(end_time_str) > 8:  # 包含日期的格式
                    end_time_str = (
                        end_time_str.split(" ")[1]
                        if " " in end_time_str
                        else end_time_str[-8:]
                    )

                current_time_str = current_time.strftime("%H:%M:%S")
                return start_time_str <= current_time_str <= end_time_str

            elif time_type == "month":
                # 每月时间范围：先检查是否是指定的日期，再检查时间范围
                month_day = suppression_time.get("week_month")
                current_day = str(current_time.day)

                # 如果不是指定的日期，直接返回False
                if int(current_day) not in month_day:
                    return False

                # 检查时间范围
                start_time_str = suppression_time.get("start_time")
                end_time_str = suppression_time.get("end_time")

                # 如果没有配置时间范围，则只要日期匹配就符合条件
                if not start_time_str or not end_time_str:
                    return True

                # 只比较时间部分（HH:MM:SS）
                if len(start_time_str) > 8:  # 包含日期的格式
                    start_time_str = (
                        start_time_str.split(" ")[1]
                        if " " in start_time_str
                        else start_time_str[-8:]
                    )
                if len(end_time_str) > 8:  # 包含日期的格式
                    end_time_str = (
                        end_time_str.split(" ")[1]
                        if " " in end_time_str
                        else end_time_str[-8:]
                    )

                current_time_str = current_time.strftime("%H:%M:%S")
                return start_time_str <= current_time_str <= end_time_str

        except ValueError as e:
            logger.error(f"Error parsing time format: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error checking shield time range: {str(e)}")
            return False

        return True

    def shield(self):
        """
        事件屏蔽主入口
        内容+时间
        参考告警自动分派
        """
        return self.execute_shield_check()


def execute_shield_check_for_events(event_ids: List[str], active_shields=None) -> Dict[str, Any]:
    """
    为指定事件列表执行屏蔽检查（性能优化版）

    Args:
        event_ids: 事件ID列表
        active_shields: 预加载的活跃屏蔽策略（可选，避免重复查询）

    Returns:
        执行结果
    """
    logger.info("=== Starting shield check for events ===")
    if not event_ids:
        return {
            "total_events": 0,
            "shielded_events": 0,
            "unshielded_events": 0,
            "shield_results": [],
        }
    
    # 优化：如果没有传入 active_shields，检查是否有活跃策略
    if active_shields is None:
        # 未传入，需要查询
        try:
            operator = EventShieldOperator(event_ids)
        except ShieldNotFoundError:
            logger.warning("No active shields found, skipping shield check")
            return {
                "total_events": len(event_ids),
                "shielded_events": 0,
                "unshielded_events": len(event_ids),
                "shield_results": [],
            }
        except EventNotFoundError:
            logger.warning("No events found for shielding, skipping shield check")
            return {
                "total_events": 0,
                "shielded_events": 0,
                "unshielded_events": 0,
                "shield_results": [],
            }
    else:
        # 已传入，直接使用（避免重复查询）
        if not active_shields or not active_shields.exists():
            logger.debug("No active shields provided, skipping shield check")
            return {
                "total_events": len(event_ids),
                "shielded_events": 0,
                "unshielded_events": len(event_ids),
                "shield_results": [],
            }
        try:
            operator = EventShieldOperator(event_ids, active_shields=active_shields)
        except EventNotFoundError:
            logger.warning("No events found for shielding, skipping shield check")
            return {
                "total_events": 0,
                "shielded_events": 0,
                "unshielded_events": 0,
                "shield_results": [],
            }
    
    result = operator.execute_shield_check()
    logger.info(f"=== Shield check completed: {result} ===")
    return result
