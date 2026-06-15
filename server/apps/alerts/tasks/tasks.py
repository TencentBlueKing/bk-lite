# -- coding: utf-8 --
# @File: tasks.py
# @Time: 2025/5/9 14:56
# @Author: windyzhao
import time
from typing import Iterable, List

from celery import shared_task

from apps.alerts.common.notify.notify import Notify
from apps.alerts.models.sys_setting import SystemSetting
from apps.alerts.service.notify_service import NotifyResultService
from apps.alerts.service.un_dispatch import UnDispatchService
from apps.core.logger import alert_logger as logger


AUTO_ASSIGNMENT_CHUNK_SIZE = 200


def _chunk_alert_ids(alert_ids: List[str], chunk_size: int) -> Iterable[List[str]]:
    for i in range(0, len(alert_ids), chunk_size):
        yield alert_ids[i : i + chunk_size]


@shared_task
def event_aggregation_alert():
    """执行告警聚合任务（周期性调度）"""
    logger.info("[AlertTask] 开始执行告警聚合任务")
    from apps.alerts.aggregation.processor.aggregation_processor import (
        AggregationProcessor,
    )

    try:
        processor = AggregationProcessor()
        processor.process_aggregation()
        logger.info("[AlertTask] 告警聚合任务执行完成")

    except Exception as e:
        logger.exception("[AlertTask] 告警聚合任务执行失败: %s", e)

    try:
        from apps.alerts.aggregation.recovery.timeout_checker import TimeoutChecker

        confirmed_count = TimeoutChecker.check_session_timeouts()
        logger.info("[AlertTask] 聚合后会话超时检查完成，确认告警数=%s", confirmed_count)
    except Exception as e:
        logger.exception("[AlertTask] 聚合后会话超时检查失败: %s", e)
        raise


@shared_task
def beat_close_alert():
    """
    告警关闭兜底机制
    """
    logger.info("[AlertTask] == beat close alert task start ==")
    try:
        logger.info("[AlertTask] 开始执行告警自动关闭定时任务")
        from apps.alerts.common.auto_close import AlertAutoClose

        auto_closer = AlertAutoClose()
        auto_closer.main()
        logger.info("[AlertTask] 告警自动关闭定时任务执行完成")
    except ImportError as e:
        logger.error("[AlertTask] 自动关闭模块导入失败: %s", e)
        raise
    except Exception as e:
        logger.error("[AlertTask] 告警自动关闭定时任务执行失败: %s", e, exc_info=True)
        raise
    logger.info("[AlertTask] == beat close alert task end ==")


@shared_task
def check_and_send_reminders():
    """
    统一的提醒检查任务 - 每分钟执行一次轮询
    检查所有需要发送提醒的告警并处理
    """
    logger.info("[AlertTask] == 开始检查提醒任务 ==")
    try:
        from apps.alerts.service.reminder_service import ReminderService

        result = ReminderService.check_and_process_reminders()
        logger.info(
            "[AlertTask] == 提醒任务检查完成 == 处理=%s, 成功=%s",
            result.get("processed", 0), result.get("success", 0),
        )
        return result
    except Exception as e:
        logger.error("[AlertTask] 提醒任务检查失败: %s", e, exc_info=True)
        return {"processed": 0, "success": 0, "error": str(e)}


@shared_task
def cleanup_reminder_tasks():
    """
    清理过期的提醒任务记录
    每小时执行一次
    """
    logger.info("[AlertTask] == 开始清理提醒任务 ==")
    try:
        from apps.alerts.service.reminder_service import ReminderService

        cleaned_count = ReminderService.cleanup_expired_reminders()
        from apps.alerts.service.escalation_service import EscalationService
        EscalationService.cleanup_expired_escalations()
        logger.info("[AlertTask] == 提醒任务清理完成 == 清理了 %s 条记录", cleaned_count)
        return cleaned_count
    except Exception as e:
        logger.error("[AlertTask] 清理提醒任务失败: %s", e, exc_info=True)


@shared_task
def check_and_send_escalations():
    """统一的升级检查任务 - 每分钟执行一次轮询"""
    logger.info("[AlertTask] == 开始检查升级任务 ==")
    try:
        from apps.alerts.service.escalation_service import EscalationService

        result = EscalationService.check_and_process_escalations()
        logger.info(
            "[AlertTask] == 升级任务检查完成 == 处理=%s, 升级=%s",
            result.get("processed", 0), result.get("escalated", 0),
        )
        return result
    except Exception as e:
        logger.error("[AlertTask] 升级任务检查失败: %s", e, exc_info=True)
        return {"processed": 0, "escalated": 0, "error": str(e)}


@shared_task
def async_auto_assignment_for_alerts(alert_ids):
    """
    异步执行告警自动分配

    Args:
        alert_ids: 告警ID列表

    Returns:
        执行结果统计
    """
    if not alert_ids:
        logger.info("[AlertTask] 无告警需要自动分配")
        return {"total_alerts": 0, "assigned_alerts": 0}

    unique_alert_ids = list(dict.fromkeys(alert_ids))
    logger.info(
        "[AlertTask] 自动分配任务接收告警: original=%s, unique=%s, chunk_size=%s",
        len(alert_ids),
        len(unique_alert_ids),
        AUTO_ASSIGNMENT_CHUNK_SIZE,
    )

    if len(unique_alert_ids) > AUTO_ASSIGNMENT_CHUNK_SIZE:
        chunks = list(_chunk_alert_ids(unique_alert_ids, AUTO_ASSIGNMENT_CHUNK_SIZE))
        for chunk in chunks:
            async_auto_assignment_for_alerts.delay(chunk)

        logger.info(
            "[AlertTask] 自动分配任务已分片调度: unique=%s, chunk_count=%s, chunk_size=%s",
            len(unique_alert_ids),
            len(chunks),
            AUTO_ASSIGNMENT_CHUNK_SIZE,
        )
        return {
            "total_alerts": len(unique_alert_ids),
            "assigned_alerts": 0,
            "failed_alerts": 0,
            "chunked": True,
            "chunk_size": AUTO_ASSIGNMENT_CHUNK_SIZE,
            "chunk_count": len(chunks),
        }

    logger.info("[AlertTask] == 开始异步自动分配告警 == 告警数量: %s", len(unique_alert_ids))

    try:
        from apps.alerts.common.assignment import execute_auto_assignment_for_alerts

        result = execute_auto_assignment_for_alerts(unique_alert_ids)
        logger.info(
            "[AlertTask] == 异步自动分配完成 == 总数=%s, 成功=%s, 失败=%s",
            result.get("total_alerts", 0),
            result.get("assigned_alerts", 0),
            result.get("failed_alerts", 0),
        )
        return result

    except Exception as e:
        logger.error("[AlertTask] 异步自动分配失败: %s", e, exc_info=True)
        return {
            "total_alerts": len(unique_alert_ids),
            "assigned_alerts": 0,
            "error": str(e),
        }


@shared_task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def build_instant_alerts(hits_payload):
    """即时告警异步兜底任务。

    仅在 InstantAlertDispatcher 检测到命中数超过 INSTANT_SYNC_THRESHOLD 时
    被调度。任务内部完成 bulk_create Alert + M2M + 触发异步分派。

    Args:
        hits_payload: [{"strategy_id": int, "event_id": str}, ...]
    """
    if not hits_payload:
        return {"created": 0}

    from apps.alerts.aggregation.processor.instant_dispatcher import (
        InstantHit,
        _bulk_build_instant_alerts,
        _trigger_dispatch_async,
    )

    hits = [
        InstantHit(strategy_id=item["strategy_id"], event_id=item["event_id"])
        for item in hits_payload
        if isinstance(item, dict) and "strategy_id" in item and "event_id" in item
    ]
    alert_ids = _bulk_build_instant_alerts(hits)
    logger.info(
        "[AlertTask] instant async build_instant_alerts done: hits=%s created=%s",
        len(hits),
        len(alert_ids),
    )
    if alert_ids:
        _trigger_dispatch_async(alert_ids)
    return {"created": len(alert_ids)}


@shared_task
def sync_notify(params):
    """
    同步通知方法
    :param params: 通知参数列表，每个元素是一个字典，包含以下键：
        : username_list: 用户名列表
        : channel_id: 通知渠道ID
        : channel_type: 通知渠道类型
        : title: 通知标题
        : content: 通知内容
        : object_id: 通知对象ID（可选）
        : notify_action_object: 通知动作对象，默认为"alert"
    """
    send_time = time.time()
    result_list = []
    for param in params:
        username_list = param["username_list"]
        channel_id = param["channel_id"]
        channel_type = param["channel_type"]
        title = param["title"]
        content = param["content"]
        object_id = param.get("object_id", "")
        notify_action_object = param.get("notify_action_object", "alert")
        logger.info(
            "[AlertTask] === 开始执行通知任务 time=%s username_list=%s, channel=%s ===",
            send_time, username_list, channel_type,
        )
        notify = Notify(
            username_list=username_list,
            channel_id=channel_id,
            title=title,
            content=content,
        )
        result = notify.notify()
        result_list.append(result)
        logger.info("[AlertTask] === 通知任务执行完成 send_time=%s ===", send_time)
        if object_id:
            notify_result_obj = NotifyResultService(
                notify_users=username_list,
                channel=channel_type,
                notify_object=object_id,
                notify_action_object=notify_action_object,
                notify_result=result,
            )
            notify_result_obj.save_notify_result()

    return result_list


@shared_task
def sync_shield(event_list):
    """
    异步屏蔽事件
    """
    logger.info("[AlertTask] == 开始执行屏蔽事件任务 ==")
    try:
        from apps.alerts.common.shield import execute_shield_check_for_events

        result = execute_shield_check_for_events(event_list)
        logger.info("[AlertTask] == 屏蔽事件任务完成 == 处理了 %s 条事件", len(event_list))
        return result
    except Exception as e:
        logger.error("[AlertTask] 屏蔽事件任务失败: %s", e, exc_info=True)
        return {"result": False, "error": str(e)}


@shared_task
def sync_no_dispatch_alert_notice_task():
    """
    周期任务，检查那些未能自动分派的告警，进行系统配置的通知
    """
    logger.info("[AlertTask] == 开始执行未分派告警通知任务 ==")
    setting_activate = SystemSetting.objects.filter(
        key="no_dispatch_alert_notice", is_activate=True
    ).exists()
    if not setting_activate:
        logger.info("[AlertTask] == 未分派告警通知功能未启用，任务执行结束 ==")
        return

    params = UnDispatchService.notify_un_dispatched_alert_params_format()
    sync_notify(params=params)

    logger.info("[AlertTask] == 未分派告警通知任务执行完成 ==")
