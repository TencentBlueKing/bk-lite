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
    SYSTEM_OPERATOR_USER,
)
from apps.alerts.service.alter_operator import AlertOperator
from apps.alerts.service.un_dispatch import UnDispatchService
from apps.alerts.utils.time_range_checker import TimeRangeChecker
from apps.alerts.utils.rule_matcher import RuleMatcher
from apps.alerts.utils.operator_log import record_operator_logs_bulk
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
        "source_id": "events__source_id",
        "source_name": "source_name",
        # 前端 matchRule 组件下发的级别条件 key 是 `level`（分派弹窗用默认 ruleList），
        # value 为 level_id；Alert.level 存的也是 level_id。保留 `level_id` 兼容历史数据。
        "level": "level",
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
        # TODO(多策略都生效): 当前为"先到先得+排他"——按 created_at 最早创建的命中策略
        #   抢走告警，后续策略因 assigned_alert_ids 被排除而拿不到。导致一个告警即使命中
        #   多个策略，也只有一个策略生效(处理人/通知/提醒/升级都来自它)。
        #   期望改为"逐告警聚合命中"：收集某告警命中的全部策略 → 处理人取并集、每个策略各发
        #   自己的通知(含 opspilot)。注意约束：AlertReminderTask/AlertEscalationTask 的 alert
        #   是 OneToOne 主键，一个告警只能存一份提醒/升级任务——若要每个策略各自独立提醒/升级，
        #   需把这两张表 OneToOne→FK + unique(alert, assignment) 并写数据迁移。详见探讨记录。
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
                        alert_pk = result.get("alert_pk")
                        if alert_pk is not None:
                            assigned_alert_ids.add(alert_pk)
                    else:
                        results["failed_alerts"] += 1

                try:
                    self._batch_create_log(assignment, matched_alert_ids)
                except Exception as log_error:
                    logger.error(
                        "[AlertAssign] 创建分派日志失败 assignment_id=%s: %s",
                        assignment.id, log_error, exc_info=True,
                    )

            except Exception as e:
                logger.error("[AlertAssign] 处理分派失败 assignment_id=%s: %s", assignment.id, e, exc_info=True)
                continue

        logger.info("[AlertAssign] 分派处理完成: %s", results)
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
        record_operator_logs_bulk(bulk_data)

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
        base_queryset = Alert.objects.filter(
            alert_id__in=self.alert_id_list, status=AlertStatus.UNASSIGNED
        ).exclude(
            is_session_alert=True,
            session_status__in=SessionStatus.NO_CONFIRMED,
        )

        # 排除已分派的告警
        if excluded_ids:
            base_queryset = base_queryset.exclude(id__in=excluded_ids)

        # 按分派策略的时间范围过滤告警
        # 优先尝试将时间范围下推到数据库（利用 created_at 索引），
        # 仅当 type 不支持 SQL 下推（day/week/month 循环型）时才退化到 Python 遍历。
        checker_proto = TimeRangeChecker(assignment.config)
        orm_filter = checker_proto.to_orm_filter("created_at")

        if orm_filter is not None:
            # 快速路径：一次性时段（type=one）或无配置 → 全在 DB 完成，无 Python 遍历
            time_filtered_queryset = base_queryset.filter(orm_filter)
            time_matched_alert_ids = list(time_filtered_queryset.values_list("id", flat=True))
        else:
            # 退化路径：循环型时段（day/week/month）→ Python 层逐行判断
            time_matched_alert_ids = []
            for alert_pk, created_at in base_queryset.values_list("id", "created_at"):
                checker = TimeRangeChecker(assignment.config, created_at)
                if checker.is_in_range():
                    time_matched_alert_ids.append(alert_pk)
            time_filtered_queryset = Alert.objects.filter(id__in=time_matched_alert_ids)

        if not time_matched_alert_ids:
            logger.debug("[AlertAssign] 无告警匹配分派时间范围 assignment_id=%s", assignment.id)
            return []

        if assignment.match_type == AlertAssignmentMatchType.ALL:
            # 全部匹配，返回所有时间范围匹配且未分派的告警
            return time_matched_alert_ids

        elif assignment.match_type == AlertAssignmentMatchType.FILTER:
            # 过滤匹配，使用规则匹配器
            matched_ids = self.rule_matcher.filter_queryset(
                time_filtered_queryset, assignment.match_rules or []
            )
            return list(dict.fromkeys(matched_ids))

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
                alert = self.alerts.get(alert_id)
                results.append(
                    {
                        "alert_id": alert.alert_id if alert else alert_id,
                        "alert_pk": alert_id,
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
                                    "alert_pk": alert.id,
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
                            user=SYSTEM_OPERATOR_USER
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
                            "[AlertAssign] 告警 %s 成功分派给 %s, result=%s",
                            alert.alert_id, personnel, result,
                        )

                        # 分派通知已在 operate("assign") 内经 transaction.on_commit 发送（见
                        # AlertOperator._assign_alert）。此处不再额外触发一次"立即提醒"，避免
                        # 处理人一次收到两条；后续提醒由 check_and_send_reminders 周期触发。

                        results.append(
                            {
                                "alert_id": alert.alert_id,
                                "alert_pk": alert.id,
                                "success": True,
                                "assignment_id": assignment.id,
                                "assigned_to": personnel,
                            }
                        )

                    except Exception as e:
                        logger.exception(
                            "[AlertAssign] 执行分派失败 alert_id=%s", alert.alert_id
                        )
                        results.append(
                            {
                                "alert_id": alert.alert_id,
                                "alert_pk": alert.id,
                                "success": False,
                                "message": str(e),
                                "assignment_id": assignment.id,
                            }
                        )

        except Exception as e:
            logger.error("[AlertAssign] 批量分派失败: %s", e, exc_info=True)
            # 如果批量操作失败，为所有告警添加失败记录
            for alert_id in alert_ids:
                alert = self.alerts.get(alert_id)
                results.append(
                    {
                        "alert_id": alert.alert_id if alert else alert_id,
                        "alert_pk": alert_id,
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
    logger.info("[AlertAssign] === 自动分派完成: %s ===", result)
    # 兜底口径以"仍为未分派"为准，而非"是否出现在结果里"：
    # 匹配到策略但分派失败的告警也应进入兜底，否则会在即时兜底中被漏掉。
    # 排除仍在观察期的会话告警（与 _batch_find_matching_alerts 口径一致）。
    not_assignment_ids = set(
        Alert.objects.filter(
            alert_id__in=alert_ids, status=AlertStatus.UNASSIGNED
        )
        .exclude(
            is_session_alert=True,
            session_status__in=SessionStatus.NO_CONFIRMED,
        )
        .values_list("alert_id", flat=True)
    )
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
    params = UnDispatchService.notify_un_dispatched_alert_params_format(
        alerts=alert_instances
    )
    from apps.alerts.common.notify.dispatcher import enqueue_notifications

    enqueue_notifications(params)
