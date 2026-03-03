# -- coding: utf-8 --
# @File: tasks.py
# @Time: 2025/5/9 14:56
# @Author: windyzhao
import time

from celery import shared_task

from apps.alerts.common.notify.notify import Notify
from apps.alerts.models.sys_setting import SystemSetting
from apps.alerts.service.notify_service import NotifyResultService
from apps.alerts.service.un_dispatch import UnDispatchService
from apps.core.logger import alert_logger as logger


@shared_task
def event_aggregation_alert():
    """执行告警聚合任务（周期性调度）"""
    logger.info("开始执行告警聚合任务")
    from apps.alerts.aggregation.processor.aggregation_processor import (
        AggregationProcessor,
    )

    try:
        processor = AggregationProcessor()
        processor.process_aggregation()
        logger.info("告警聚合任务执行完成")

    except Exception as e:
        logger.exception(f"告警聚合任务执行失败: {e}")

    try:
        from apps.alerts.aggregation.recovery.timeout_checker import TimeoutChecker

        confirmed_count = TimeoutChecker.check_session_timeouts()
        logger.info(f"聚合后会话超时检查完成，确认告警数={confirmed_count}")
    except Exception as e:
        logger.exception(f"聚合后会话超时检查失败: {e}")
        raise


@shared_task
def beat_close_alert():
    """
    告警关闭兜底机制
    """
    logger.info("== beat close alert task start ==")
    try:
        logger.info("开始执行告警自动关闭定时任务")
        from apps.alerts.common.auto_close import AlertAutoClose

        auto_closer = AlertAutoClose()
        auto_closer.main()
        logger.info("告警自动关闭定时任务执行完成")
    except ImportError as e:
        logger.error(f"自动关闭模块导入失败: {str(e)}")
        raise
    except Exception as e:
        import traceback

        logger.error(
            f"告警自动关闭定时任务执行失败: {str(e)}\n"
            f"堆栈跟踪:\n{traceback.format_exc()}"
        )
        raise
    logger.info("== beat close alert task end ==")


@shared_task
def check_and_send_reminders():
    """
    统一的提醒检查任务 - 每分钟执行一次轮询
    检查所有需要发送提醒的告警并处理
    """
    logger.info("== 开始检查提醒任务 ==")
    try:
        from apps.alerts.service.reminder_service import ReminderService

        result = ReminderService.check_and_process_reminders()
        logger.info(
            f"== 提醒任务检查完成 == 处理={result.get('processed', 0)}, 成功={result.get('success', 0)}"
        )
        return result
    except Exception as e:
        logger.error(f"提醒任务检查失败: {str(e)}")
        return {"processed": 0, "success": 0, "error": str(e)}


@shared_task
def cleanup_reminder_tasks():
    """
    清理过期的提醒任务记录
    每小时执行一次
    """
    logger.info("== 开始清理提醒任务 ==")
    try:
        from apps.alerts.service.reminder_service import ReminderService

        cleaned_count = ReminderService.cleanup_expired_reminders()
        logger.info(f"== 提醒任务清理完成 == 清理了{cleaned_count}条记录")
        return cleaned_count
    except Exception as e:
        logger.error(f"清理提醒任务失败: {str(e)}")


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
        logger.info("无告警需要自动分配")
        return {"total_alerts": 0, "assigned_alerts": 0}

    logger.info(f"== 开始异步自动分配告警 == 告警数量: {len(alert_ids)}")

    try:
        from apps.alerts.common.assignment import execute_auto_assignment_for_alerts

        result = execute_auto_assignment_for_alerts(alert_ids)
        logger.info(
            f"== 异步自动分配完成 == "
            f"总数={result.get('total_alerts', 0)}, "
            f"成功={result.get('assigned_alerts', 0)}, "
            f"失败={result.get('failed_alerts', 0)}"
        )
        return result

    except Exception as e:
        import traceback
        logger.error(f"异步自动分配失败: {traceback.format_exc()}")
        return {"total_alerts": len(alert_ids), "assigned_alerts": 0, "error": str(e)}


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
            "=== 开始执行通知任务 time={} username_list={}, channel={} ===".format(
                send_time, username_list, channel_type
            )
        )
        notify = Notify(
            username_list=username_list,
            channel_id=channel_id,
            title=title,
            content=content,
        )
        result = notify.notify()
        result_list.append(result)
        logger.info("=== 通知任务执行完成 send_time={}===".format(send_time))
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
    logger.info("== 开始执行屏蔽事件任务 ==")
    try:
        from apps.alerts.common.shield import execute_shield_check_for_events

        result = execute_shield_check_for_events(event_list)
        logger.info(f"== 屏蔽事件任务完成 == 处理了{len(event_list)}条事件")
        return result
    except Exception as e:
        logger.error(f"屏蔽事件任务失败: {str(e)}")
        return {"result": False, "error": str(e)}


@shared_task
def sync_no_dispatch_alert_notice_task():
    """
    周期任务，检查那些未能自动分派的告警，进行系统配置的通知
    """
    logger.info("== 开始执行未分派告警通知任务 ==")
    setting_activate = SystemSetting.objects.filter(
        key="no_dispatch_alert_notice", is_activate=True
    ).exists()
    if not setting_activate:
        logger.info("== 未分派告警通知功能未启用，任务执行结束 ==")
        return

    params = UnDispatchService.notify_un_dispatched_alert_params_format()
    sync_notify(params=params)

    logger.info("== 未分派告警通知任务执行完成 ==")
