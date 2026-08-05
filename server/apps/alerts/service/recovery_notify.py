# -- coding: utf-8 --
"""告警恢复通知。

分派策略勾选【恢复】(notification_scenario 含 "recovery")时，在 alert 状态置为
AUTO_RECOVERY 之后，按策略的 personnel + notify_channels 发一封 title 带【恢复】
前缀的通知。复用统一出口 build_channel_params / enqueue_notifications。
"""
from typing import Optional

from apps.alerts.common.notify.base import NotifyParamsFormat
from apps.alerts.models import Alert, AlertAssignment, AlertReminderTask
from apps.core.logger import alert_logger as logger

RECOVERY_SCENARIO = "recovery"


def _find_assignment_for_alert(alert: Alert) -> Optional[AlertAssignment]:
    """通过 AlertReminderTask 反查 alert 关联的分派策略。

    恢复时 stop_reminder_task 即将/已经置 is_active=False，所以这里不过滤 is_active。
    表是 OneToOne 主键，最多一条。
    """
    task = (
        AlertReminderTask.objects.filter(alert=alert)
        .select_related("assignment")
        .first()
    )
    return task.assignment if task else None


def notify_alert_recovered(alert: Alert) -> bool:
    """告警恢复后按策略配置发【恢复】通知。

    返回 True 表示已入队；任一前置条件不满足(无策略/未勾 recovery/无接收人/无渠道)
    都返回 False 并仅打日志，不抛异常——恢复流程不应因通知失败而回滚。
    """
    assignment = _find_assignment_for_alert(alert)
    if assignment is None:
        logger.info(
            "[AlertRecoveryNotify] alert_id=%s 无关联分派策略，跳过恢复通知",
            alert.alert_id,
        )
        return False

    scenarios = assignment.notification_scenario or []
    if RECOVERY_SCENARIO not in scenarios:
        logger.info(
            "[AlertRecoveryNotify] alert_id=%s 策略 %s 未勾选恢复场景，跳过 (scenario=%s)",
            alert.alert_id, assignment.id, scenarios,
        )
        return False

    receivers = list(assignment.personnel or [])
    if not receivers:
        logger.warning(
            "[AlertRecoveryNotify] alert_id=%s 策略 %s 无分派人员，跳过",
            alert.alert_id, assignment.id,
        )
        return False

    channels = assignment.notify_channels or []
    if not channels:
        logger.warning(
            "[AlertRecoveryNotify] alert_id=%s 策略 %s 无通知渠道，跳过",
            alert.alert_id, assignment.id,
        )
        return False

    from apps.alerts.common.notify.dispatcher import (
        build_channel_params,
        enqueue_notifications,
    )

    default_title = NotifyParamsFormat(
        username_list=receivers, alerts=[alert]
    ).format_title()
    title = f"【恢复】{default_title}"

    params = build_channel_params(
        receivers, channels, [alert], alert.alert_id, title=title,
    )
    if not params:
        logger.warning(
            "[AlertRecoveryNotify] alert_id=%s 构造通知参数为空，跳过",
            alert.alert_id,
        )
        return False

    ok = enqueue_notifications(
        params, idempotency_key=f"recovery-notify:{alert.alert_id}",
    )
    logger.info(
        "[AlertRecoveryNotify] alert_id=%s assignment_id=%s 恢复通知入队=%s 接收人=%s 渠道=%s",
        alert.alert_id, assignment.id, ok, receivers,
        [(p.get("channel_type"), p.get("channel_id")) for p in params],
    )
    return ok
