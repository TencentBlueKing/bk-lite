# -- coding: utf-8 --
# @File: assignment.py
# @Time: 2025/6/10 17:43
# @Author: windyzhao
from typing import List, Dict, Any, Optional

from django.utils import timezone
from django.db import transaction

from apps.alerts.error import AlertNotFoundError
from apps.alerts.models.operator_log import OperatorLog
from apps.alerts.models.models import Alert
from apps.alerts.models.alert_operator import AlertAssignment
from apps.alerts.constants.constants import (
    AlertStatus,
    AlertAssignmentMatchType,
    LogAction,
    LogTargetType,
    SessionStatus,
)
from apps.alerts.service.alter_operator import AlertOperator
from apps.alerts.service.reminder_service import ReminderService
from apps.alerts.service.un_dispatch import UnDispatchService
from apps.alerts.utils.time_range_checker import TimeRangeChecker
from apps.alerts.utils.rule_matcher import RuleMatcher
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

    # 字段映射到模型字段
    FIELD_MAPPING = {
        "source_id": "source_name",
        "level_id": "level",
        "resource_type": "resource_type",
        "resource_id": "resource_id",
        "content": "content",
        "title": "title",
        "alert_id": "alert_id",
    }

    def __init__(self, alert_id_list: List[str]):
        self.alert_id_list = alert_id_list
        self.alerts = self.get_alert_map()
        if not self.alerts:
            raise AlertNotFoundError("No alerts found for the provided alert_id_list")
        # 初始化规则匹配器
        self.rule_matcher = RuleMatcher(self.FIELD_MAPPING)

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
                "assignment_results": [],
            }

        # 获取所有活跃的分派策略
        active_assignments = AlertAssignment.objects.filter(is_active=True).order_by(
            "created_at"
        )

        results = {
            "total_alerts": len(self.alerts),
            "assigned_alerts": 0,
            "failed_alerts": 0,
            "assignment_results": [],
        }

        # 记录已分派的告警ID，避免重复分派
        assigned_alert_ids = set()

        # 按分派策略批量处理告警
        for assignment in active_assignments:
            try:
                # 批量查找匹配该分派策略的告警（包含时间范围和内容过滤，排除已分派的）
                matched_alert_ids = self._batch_find_matching_alerts(
                    assignment, assigned_alert_ids
                )

                if not matched_alert_ids:
                    continue

                # 批量执行分派操作
                assignment_results = self._batch_execute_assignment(
                    matched_alert_ids, assignment
                )
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
                    logger.error(
                        f"Error creating logs for assignment {assignment.id}: {str(log_error)}"
                    )

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

    def _batch_find_matching_alerts(
            self, assignment: AlertAssignment, excluded_ids: set = None
    ) -> List[int]:
        """
        批量查找匹配指定分派策略的告警ID列表

        Args:
            assignment: 分派策略
            excluded_ids: 需要排除的告警ID集合

        Returns:
            匹配的告警ID列表
        """
        # 先过滤未分派状态的告警
        base_queryset = (
            Alert.objects.filter(alert_id__in=self.alert_id_list, status=AlertStatus.UNASSIGNED)
            .exclude(
                is_session_alert=True,
                session_status__in=SessionStatus.NO_CONFIRMED,
            )
        )

        # 排除已分派的告警
        if excluded_ids:
            base_queryset = base_queryset.exclude(id__in=excluded_ids)

        # 首先按照Alert的created_at时间过滤符合分派策略时间范围的告警
        time_matched_alert_ids = []
        for alert in base_queryset:
            checker = TimeRangeChecker(assignment.config, alert.created_at)
            if checker.is_in_range():
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
            # 过滤匹配，使用规则匹配器
            return self.rule_matcher.filter_queryset(
                time_filtered_queryset, assignment.match_rules or []
            )

        return []

    def _batch_execute_assignment(
            self, alert_ids: List[int], assignment: AlertAssignment
    ) -> List[Dict[str, Any]]:
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
                results.append(
                    {
                        "alert_id": alert_id,
                        "success": False,
                        "message": "No personnel configured for assignment",
                        "assignment_id": assignment.id,
                    }
                )
            return results

        try:
            with transaction.atomic():
                # 批量获取告警实例
                alerts = Alert.objects.filter(
                    id__in=alert_ids, status=AlertStatus.UNASSIGNED
                )

                for alert in alerts:
                    try:
                        if (
                            alert.is_session_alert
                            and alert.session_status != SessionStatus.CONFIRMED
                        ):
                            logger.info(
                                "跳过会话观察期告警的自动分派: alert_id=%s, session_status=%s",
                                alert.alert_id,
                                alert.session_status,
                            )
                            results.append(
                                {
                                    "alert_id": alert.alert_id,
                                    "success": False,
                                    "assignment_id": assignment.id,
                                    "assigned_to": [],
                                    "message": "session alert observing",
                                    "skip_session_alert": True,
                                }
                            )
                            continue
                        # 使用AlertOperator执alert.alert_id行分派操作
                        operator = AlertOperator(
                            user="admin"
                        )  # 假设使用admin用户执行操作

                        # 执行分派操作
                        result = operator.operate(
                            action="assign",
                            alert_id=alert.alert_id,
                            data={
                                "assignee": personnel,
                                "assignment_id": assignment.id,
                            },
                        )
                        logger.debug(
                            f"Alert {alert.alert_id} assigned successfully to {personnel}, result={result}"
                        )

                        # 创建提醒记录（如果配置了通知频率）
                        if assignment.notification_frequency:
                            operator._create_reminder_record(alert, str(assignment.id))

                        logger.info(
                            "== assignment alert notify start ==, assignment={}, alert_id={}".format(
                                assignment.id, alert.alert_id
                            )
                        )
                        # 分派成功后 立即发送提醒通知
                        ReminderService._send_reminder_notification(
                            assignment=assignment, alert=alert
                        )
                        logger.info(
                            "== assignment alert notify end ==, assignment={}, alert_id={}".format(
                                assignment.id, alert.alert_id
                            )
                        )

                        results.append(
                            {
                                "alert_id": alert.alert_id,
                                "success": True,
                                "assignment_id": assignment.id,
                                "assigned_to": personnel,
                            }
                        )

                    except Exception as e:
                        import traceback

                        logger.error(
                            f"Error executing assignment for alert {alert.alert_id}: {traceback.format_exc()}"
                        )
                        results.append(
                            {
                                "alert_id": alert.alert_id,
                                "success": False,
                                "message": str(e),
                                "assignment_id": assignment.id,
                            }
                        )

        except Exception as e:
            logger.error(f"Error in batch assignment: {str(e)}")
            # 如果批量操作失败，为所有告警添加失败记录
            for alert_id in alert_ids:
                results.append(
                    {
                        "alert_id": alert_id,
                        "success": False,
                        "message": str(e),
                        "assignment_id": assignment.id,
                    }
                )

        return results


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
            "assignment_results": [],
        }

    operator = AlertAssignmentOperator(alert_ids)
    result = operator.execute_auto_assignment()
    logger.info(f"=== Auto assignment completed: {result} ===")
    assignment_alart_ids = [
        i.get("alert_id") for i in result.get("assignment_results", [])
    ]
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
    alert_instances = list(
        Alert.objects.filter(alert_id__in=alert_ids, status=AlertStatus.UNASSIGNED)
    )
    from apps.alerts.tasks import sync_notify

    params = UnDispatchService.notify_un_dispatched_alert_params_format(
        alerts=alert_instances
    )
    sync_notify.delay(params)
