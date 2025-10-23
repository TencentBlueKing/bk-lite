# -- coding: utf-8 --
# @File: assignment.py
# @Time: 2025/6/10 17:43
# @Author: windyzhao
from datetime import datetime
from typing import List, Dict, Any, Optional

from django.db.models import Q
from django.utils import timezone
from django.db import transaction

from apps.alerts.error import AlertNotFoundError
from apps.alerts.models import Alert, AlertAssignment, OperatorLog
from apps.alerts.constants import AlertStatus, AlertAssignmentMatchType, LogAction, LogTargetType
from apps.alerts.service.alter_operator import AlertOperator
from apps.alerts.service.reminder_service import ReminderService
from apps.alerts.service.un_dispatch import UnDispatchService
from apps.core.logger import alert_logger as logger


class AlertAssignmentOperator:
    """
    告警创建后，进行告警自动分派的操作，把符合时间范围的，匹配条件的告警分派给指定的用户。

    # 匹配条件 最外层是或关系，里层的[]是且的关系
    match_rules_dict = [
        [{
            "key": "",  # key  source_id 告警源id，level_id 级别id，resource_type 类型对象，resource_id 资源id, content 内容
            "operator": "",  # 逻辑符 "eq" 等于，"ne" 不等于，"contains" 包含，"not_contains" 不包含 re 正则表达式匹配
            "value": "",  # value 匹配值

        },
        {
            "key": "",  # key  source_id 告警源id，level_id 级别id，resource_type 类型对象，resource_id 资源id, content 内容
            "operator": "",  # 逻辑符 "eq" 等于，"ne" 不等于，"contains" 包含，"not_contains" 不包含 re 正则表达式匹配
            "value": "",  # value 匹配值

        }],
        [],
        []
    ]

    # 时间范围
    config_ex = {
        "type": "one",  # 有4种， one, day , week, month
        "end_time": "2024-04-13 15:12:12",  # 开始时间
        "start_time": "2024-03-12 14:12:12",  # 结束时间
        "week_month": "1"  # 当是月或者周的时候，存储是第几月/周
    }

    每个级别的通知时间不一样
    notification_frequency = {
        "0": {
            "max_count": 10,
            "interval_minutes": 30
        }
    }
    """

    def __init__(self, alert_id_list: List[str]):
        self.alert_id_list = alert_id_list
        self.alerts = self.get_alert_map()
        if not self.alerts:
            raise AlertNotFoundError("No alerts found for the provided alert_id_list")
        # 字段映射到模型字段
        self.field_mapping = {
            "source_id": "source_name",
            "level_id": "level",
            "resource_type": "resource_type",
            "resource_id": "resource_id",
            "content": "content",
            "title": "title",
            "alert_id": "alert_id"
        }

    def get_alert_map(self) -> Dict[int, Alert]:
        """获取告警实例映射"""
        result = {}
        alerts = Alert.objects.filter(alert_id__in=self.alert_id_list)
        for alert in alerts:
            result[alert.id] = alert
        return result

    def execute_auto_assignment(self) -> Dict[str, Any]:
        """
        执行自动分派主流程 - 优化版本

        Returns:
            Dict[str, Any]: 执行结果统计
        """
        if not self.alerts:
            logger.warning("No alerts found for assignment")
            return {
                "total_alerts": 0,
                "assigned_alerts": 0,
                "failed_alerts": 0,
                "assignment_results": []
            }

        # 获取所有活跃的分派策略
        active_assignments = AlertAssignment.objects.filter(is_active=True).order_by('created_at')

        results = {
            "total_alerts": len(self.alerts),
            "assigned_alerts": 0,
            "failed_alerts": 0,
            "assignment_results": []
        }

        # 记录已分派的告警ID，避免重复分派
        assigned_alert_ids = set()

        # 按分派策略批量处理告警
        for assignment in active_assignments:
            try:
                # 批量查找匹配该分派策略的告警（包含时间范围和内容过滤，排除已分派的）
                matched_alert_ids = self._batch_find_matching_alerts(assignment, assigned_alert_ids)

                if not matched_alert_ids:
                    continue

                # 批量执行分派操作
                assignment_results = self._batch_execute_assignment(matched_alert_ids, assignment)
                results["assignment_results"].extend(assignment_results)

                # 统计结果并记录已分派的告警
                for result in assignment_results:
                    if result["success"]:
                        results["assigned_alerts"] += 1
                        assigned_alert_ids.add(result["alert_id"])
                    else:
                        results["failed_alerts"] += 1

                try:
                    self._batch_create_log(assignment, matched_alert_ids)
                except Exception as log_error:
                    logger.error(f"Error creating logs for assignment {assignment.id}: {str(log_error)}")

            except Exception as e:
                logger.error(f"Error processing assignment {assignment.id}: {str(e)}")
                continue

        logger.info(f"Assignment completed: {results}")
        return results

    @staticmethod
    def _batch_create_log(assignment: AlertAssignment, alert_ids: List[int]) -> None:
        """
        批量创建分派日志记录
        Args:
            assignment: 分派策略
            alert_ids: 告警ID列表
        """
        bulk_data = []
        for alert_id in alert_ids:
            bulk_data.append(
                OperatorLog(
                    action=LogAction.MODIFY,
                    target_type=LogTargetType.ALERT,
                    operator="system",
                    operator_object="告警处理-自动分派",
                    target_id=alert_id,
                    overview=f"告警自动分派，分派策略ID [{assignment.id}] 策略名称 [{assignment.name}] 分派人员 {assignment.personnel}",
                )
            )
        OperatorLog.objects.bulk_create(bulk_data)

    def _batch_find_matching_alerts(self, assignment: AlertAssignment, excluded_ids: set = None) -> List[int]:
        """
        批量查找匹配指定分派策略的告警ID列表
        
        Args:
            assignment: 分派策略
            excluded_ids: 需要排除的告警ID集合
            
        Returns:
            匹配的告警ID列表
        """
        # 先过滤未分派状态的告警
        base_queryset = Alert.objects.filter(
            alert_id__in=self.alert_id_list,
            status=AlertStatus.UNASSIGNED
        )

        # 排除已分派的告警
        if excluded_ids:
            base_queryset = base_queryset.exclude(id__in=excluded_ids)

        # 首先按照Alert的created_at时间过滤符合分派策略时间范围的告警
        time_matched_alert_ids = []
        for alert in base_queryset:
            if self._check_time_range(assignment.config, alert.created_at):
                time_matched_alert_ids.append(alert.id)

        if not time_matched_alert_ids:
            logger.debug(f"No alerts match time range for assignment {assignment.id}")
            return []

        # 重新构建查询集，只包含时间范围匹配的告警
        time_filtered_queryset = Alert.objects.filter(id__in=time_matched_alert_ids)

        if assignment.match_type == AlertAssignmentMatchType.ALL:
            # 全部匹配，返回所有时间范围匹配且未分派的告警
            return time_matched_alert_ids

        elif assignment.match_type == AlertAssignmentMatchType.FILTER:
            # 过滤匹配，使用ORM查询
            return self._orm_filter_alerts(time_filtered_queryset, assignment.match_rules or [])

        return []

    def _orm_filter_alerts(self, queryset, match_rules: List[List[Dict[str, Any]]]) -> List[int]:
        """
        使用ORM查询过滤匹配规则的告警
        
        Args:
            queryset: 基础查询集
            match_rules: 匹配规则 [[{},{}],[{},{}]]
            
        Returns:
            匹配的告警ID列表
        """
        if not match_rules:
            return list(queryset.values_list('id', flat=True))

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

        return list(queryset.values_list('id', flat=True))

    def _build_single_rule_q(self, rule: Dict[str, Any]) -> Optional[Q]:
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
                return Q(**{f"{model_field}__regex": value})
            else:
                logger.warning(f"Unknown operator: {operator}")
                return None

        except Exception as e:
            logger.error(f"Error building Q object for rule: {str(e)}")
            return None

    def _batch_execute_assignment(self, alert_ids: List[int], assignment: AlertAssignment) -> List[Dict[str, Any]]:
        """
        批量执行告警分派操作
        
        Args:
            alert_ids: 告警ID列表
            assignment: 分派策略
            
        Returns:
            分派结果列表
        """
        results = []

        # 获取分派人员信息
        personnel = assignment.personnel or []
        if not personnel:
            for alert_id in alert_ids:
                results.append({
                    "alert_id": alert_id,
                    "success": False,
                    "message": "No personnel configured for assignment",
                    "assignment_id": assignment.id
                })
            return results

        try:
            with transaction.atomic():
                # 批量获取告警实例
                alerts = Alert.objects.filter(id__in=alert_ids, status=AlertStatus.UNASSIGNED)

                for alert in alerts:
                    try:
                        # 使用AlertOperator执alert.alert_id行分派操作
                        operator = AlertOperator(user="admin")  # 假设使用admin用户执行操作

                        # 执行分派操作
                        result = operator.operate(
                            action="assign",
                            alert_id=alert.alert_id,
                            data={"assignee": personnel, "assignment_id": assignment.id}
                        )
                        logger.debug(f"Alert {alert.alert_id} assigned successfully to {personnel}, result={result}")

                        # 创建提醒记录（如果配置了通知频率）
                        if assignment.notification_frequency:
                            operator._create_reminder_record(alert, str(assignment.id))

                        logger.info(
                            "== assignment alert notify start ==, assignment={}, alert_id={}".format(assignment.id,
                                                                                                     alert.alert_id))
                        # 分派成功后 立即发送提醒通知
                        ReminderService._send_reminder_notification(assignment=assignment, alert=alert)
                        logger.info(
                            "== assignment alert notify end ==, assignment={}, alert_id={}".format(assignment.id,
                                                                                                   alert.alert_id))

                        results.append({
                            "alert_id": alert.alert_id,
                            "success": True,
                            "assignment_id": assignment.id,
                            "assigned_to": personnel
                        })

                    except Exception as e:
                        import traceback
                        logger.error(f"Error executing assignment for alert {alert.alert_id}: {traceback.format_exc()}")
                        results.append({
                            "alert_id": alert.alert_id,
                            "success": False,
                            "message": str(e),
                            "assignment_id": assignment.id
                        })

        except Exception as e:
            logger.error(f"Error in batch assignment: {str(e)}")
            # 如果批量操作失败，为所有告警添加失败记录
            for alert_id in alert_ids:
                results.append({
                    "alert_id": alert_id,
                    "success": False,
                    "message": str(e),
                    "assignment_id": assignment.id
                })

        return results

    def _check_time_range(self, config: Dict[str, Any], alert_created_at: datetime = None) -> bool:
        """
        检查指定时间（默认当前时间或Alert的created_at）是否在配置的时间范围内

        Args:
            config: 配置信息
            alert_created_at: Alert的创建时间，如果为None则使用当前时间

        Returns:
            bool: 是否在时间范围内
        """
        if not config:
            return True

        time_type = config.get("type", "one")
        check_time = alert_created_at if alert_created_at else timezone.now()

        try:
            if time_type == "one":
                # 一次性时间范围
                start_time_str = config.get("start_time")
                end_time_str = config.get("end_time")

                # 如果没有配置时间范围，则不符合条件
                if not start_time_str or not end_time_str:
                    logger.warning("One-time range missing start_time or end_time")
                    return False

                start_time = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S")
                end_time = datetime.strptime(end_time_str, "%Y-%m-%d %H:%M:%S")

                # 转换为带时区的时间
                start_time = timezone.make_aware(start_time)
                end_time = timezone.make_aware(end_time)

                return start_time <= check_time <= end_time

            elif time_type == "day":
                # 每日时间范围
                start_time_str = config.get("start_time")
                end_time_str = config.get("end_time")

                # 如果没有配置时间范围，则不符合条件
                if not start_time_str or not end_time_str:
                    logger.warning("Day-time range missing start_time or end_time")
                    return False

                check_time_str = check_time.strftime("%H:%M:%S")
                return start_time_str <= check_time_str <= end_time_str

            elif time_type == "week":
                # 每周时间范围：先检查是否是指定的周几，再检查时间范围
                week_day = config.get("week_month")
                current_weekday = str(check_time.weekday() + 1)  # Monday is 1

                # 如果不是指定的周几，直接返回False
                if current_weekday not in week_day:
                    return False

                # 检查时间范围
                start_time_str = config.get("start_time")
                end_time_str = config.get("end_time")

                # 如果没有配置时间范围，则只要周几匹配就符合条件
                if not start_time_str or not end_time_str:
                    return True

                # 只比较时间部分（HH:MM:SS）
                if len(start_time_str) > 8:  # 包含日期的格式
                    start_time_str = start_time_str.split(" ")[1] if " " in start_time_str else start_time_str[-8:]
                if len(end_time_str) > 8:  # 包含日期的格式
                    end_time_str = end_time_str.split(" ")[1] if " " in end_time_str else end_time_str[-8:]

                check_time_str = check_time.strftime("%H:%M:%S")
                return start_time_str <= check_time_str <= end_time_str

            elif time_type == "month":
                # 每月时间范围：先检查是否是指定的日期，再检查时间范围
                month_day = config.get("week_month")
                current_day = str(check_time.day)

                # 如果不是指定的日期，直接返回False
                if current_day not in month_day:
                    return False

                # 检查时间范围
                start_time_str = config.get("start_time")
                end_time_str = config.get("end_time")

                # 如果没有配置时间范围，则只要日期匹配就符合条件
                if not start_time_str or not end_time_str:
                    return True

                # 只比较时间部分（HH:MM:SS）
                if len(start_time_str) > 8:  # 包含日期的格式
                    start_time_str = start_time_str.split(" ")[1] if " " in start_time_str else start_time_str[-8:]
                if len(end_time_str) > 8:  # 包含日期的格式
                    end_time_str = end_time_str.split(" ")[1] if " " in end_time_str else end_time_str[-8:]

                check_time_str = check_time.strftime("%H:%M:%S")
                return start_time_str <= check_time_str <= end_time_str

        except ValueError as e:
            logger.error(f"Error parsing time format: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error checking time range: {str(e)}")
            return False

        return True


def execute_auto_assignment_for_alerts(alert_ids: List[str]) -> Dict[str, Any]:
    """
    为指定告警列表执行自动分派

    Args:
        alert_ids: 告警ID列表

    Returns:
        执行结果
    """
    logger.info("=== Starting auto assignment for alerts ===")
    if not alert_ids:
        return {
            "total_alerts": 0,
            "assigned_alerts": 0,
            "failed_alerts": 0,
            "assignment_results": []
        }

    operator = AlertAssignmentOperator(alert_ids)
    result = operator.execute_auto_assignment()
    logger.info(f"=== Auto assignment completed: {result} ===")
    assignment_alart_ids = [i.get("alert_id") for i in result.get("assignment_results", [])]
    not_assignment_ids = set(alert_ids) - set(assignment_alart_ids)
    if not_assignment_ids:
        # 去进行兜底分派 使用全局分派 每60分钟分派一次 知道告警被相应后结束
        not_assignment_alert_notify(not_assignment_ids)

    return result


def not_assignment_alert_notify(alert_ids):
    """
    获取未分派告警通知设置
    :return: SystemSetting 实例
    """
    alert_instances = list(Alert.objects.filter(alert_id__in=alert_ids, status=AlertStatus.UNASSIGNED))
    from apps.alerts.tasks import sync_notify
    params = UnDispatchService.notify_un_dispatched_alert_params_format(alerts=alert_instances)
    sync_notify.delay(params)
