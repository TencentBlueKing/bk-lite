# -- coding: utf-8 --
# @File: reminder_service.py
# @Time: 2025/6/11 10:00
# @Author: windyzhao
import json

from django.utils import timezone
from django.db import transaction
from datetime import timedelta
from typing import Dict, Any, Optional, Tuple

from apps.alerts.common.notify.base import NotifyParamsFormat
from apps.alerts.models import Alert, AlertReminderTask, AlertAssignment, Level
from apps.alerts.constants import SessionStatus, AlertStatus
from apps.core.logger import alert_logger as logger


class ReminderService:
    """告警提醒服务"""

    DEFAULT_MAX_REMINDERS = 10

    @classmethod
    def _parse_max_count(
        cls, raw_max_count: Any, *, alert_level: str, assignment_id: int
    ) -> int:
        """解析最大提醒次数。0 表示不限次数。"""
        if raw_max_count in (None, ""):
            return cls.DEFAULT_MAX_REMINDERS

        try:
            max_count = int(raw_max_count)
        except (TypeError, ValueError):
            logger.warning(
                "分派策略 %s 的提醒次数配置格式错误: level=%s, max_count=%s，使用默认值 %s",
                assignment_id,
                alert_level,
                raw_max_count,
                cls.DEFAULT_MAX_REMINDERS,
            )
            return cls.DEFAULT_MAX_REMINDERS

        if max_count < 0:
            logger.warning(
                "分派策略 %s 的提醒次数配置无效: level=%s, max_count=%s，使用默认值 %s",
                assignment_id,
                alert_level,
                raw_max_count,
                cls.DEFAULT_MAX_REMINDERS,
            )
            return cls.DEFAULT_MAX_REMINDERS

        return max_count

    @classmethod
    def _get_effective_max_reminders(cls, reminder: AlertReminderTask) -> int:
        """获取提醒任务的有效最大提醒次数。0 表示不限次数。"""
        assignment_config = reminder.assignment.notification_frequency or {}
        level_config = assignment_config.get(reminder.alert.level, {})
        if level_config:
            configured_max_count = cls._parse_max_count(
                level_config.get("max_count"),
                alert_level=reminder.alert.level,
                assignment_id=reminder.assignment_id,
            )
            if configured_max_count == 0:
                return 0

        if reminder.current_max_reminders < 0:
            return cls.DEFAULT_MAX_REMINDERS

        return reminder.current_max_reminders

    @classmethod
    def _normalize_frequency_config(
        cls, level_config: Dict[str, Any], alert_level: str, assignment_id: int
    ) -> Optional[Tuple[int, int]]:
        """规范化频率配置。"""
        if not level_config:
            return None

        interval_minutes = int(level_config.get("interval_minutes", 0) or 0)
        if interval_minutes <= 0:
            logger.warning(
                "告警级别 %s 在分派策略 %s 中没有配置有效通知频率，不创建提醒任务",
                alert_level,
                assignment_id,
            )
            return None

        max_count = cls._parse_max_count(
            level_config.get("max_count", cls.DEFAULT_MAX_REMINDERS),
            alert_level=alert_level,
            assignment_id=assignment_id,
        )

        return interval_minutes, max_count

    @classmethod
    def create_reminder_task(
        cls, alert: Alert, assignment: AlertAssignment
    ) -> Optional[AlertReminderTask]:
        """创建提醒任务"""
        try:
            # 获取该告警级别的通知频率配置
            alert_level = alert.level
            level_config = assignment.notification_frequency.get(alert_level, {})

            normalized_config = cls._normalize_frequency_config(
                level_config=level_config,
                alert_level=alert_level,
                assignment_id=assignment.id,
            )
            if not normalized_config:
                return None

            interval_minutes, max_count = normalized_config

            existing_task = AlertReminderTask.objects.filter(alert=alert).first()

            if existing_task:
                if existing_task.is_active:
                    logger.warning(f"告警 {alert.alert_id} 已存在活跃的提醒任务")
                    return existing_task

                existing_task.assignment = assignment
                existing_task.is_active = True
                existing_task.current_frequency_minutes = interval_minutes
                existing_task.current_max_reminders = max_count
                existing_task.reminder_count = 0
                existing_task.last_reminder_time = None
                existing_task.next_reminder_time = (
                    timezone.now() + timedelta(minutes=interval_minutes)
                )
                existing_task.save(
                    update_fields=[
                        "assignment",
                        "is_active",
                        "current_frequency_minutes",
                        "current_max_reminders",
                        "reminder_count",
                        "last_reminder_time",
                        "next_reminder_time",
                        "updated_at",
                    ]
                )
                logger.info(
                    "重新激活告警 %s 的提醒任务，频率: %s分钟，最大次数: %s",
                    alert.alert_id,
                    interval_minutes,
                    max_count,
                )
                return existing_task

            # 创建新的提醒任务
            reminder_task = AlertReminderTask.objects.create(
                alert=alert,
                assignment=assignment,
                is_active=True,
                current_frequency_minutes=interval_minutes,
                current_max_reminders=max_count,
                reminder_count=0,
                next_reminder_time=timezone.now() + timedelta(minutes=interval_minutes),
            )

            logger.info(
                f"为告警 {alert.alert_id} 创建提醒任务，频率: {interval_minutes}分钟，最大次数: {max_count}"
            )
            return reminder_task

        except Exception as e:
            logger.error(f"创建提醒任务失败: alert_id={alert.alert_id}, error={str(e)}")
            return None

    @classmethod
    def ensure_reminder_task(
        cls,
        alert: Alert,
        assignment: Optional[AlertAssignment] = None,
        assignment_id: Optional[int] = None,
    ) -> Optional[AlertReminderTask]:
        """确保告警存在可用的提醒任务。"""
        try:
            if assignment is None and assignment_id:
                assignment = AlertAssignment.objects.filter(
                    id=assignment_id, is_active=True
                ).first()

            if assignment is None:
                existing_task = AlertReminderTask.objects.filter(alert=alert).select_related(
                    "assignment"
                ).first()
                if existing_task:
                    assignment = existing_task.assignment

            if assignment is None:
                logger.warning(
                    "告警 %s 缺少可用的分派策略，无法恢复提醒任务",
                    alert.alert_id,
                )
                return None

            if not assignment.is_active:
                logger.warning(
                    "告警 %s 的分派策略 %s 未启用，无法恢复提醒任务",
                    alert.alert_id,
                    assignment.id,
                )
                return None

            return cls.create_reminder_task(alert, assignment)

        except Exception as e:
            logger.error(
                "确保提醒任务失败: alert_id=%s, error=%s",
                alert.alert_id,
                str(e),
            )
            return None

    @classmethod
    def stop_reminder_task(cls, alert: Alert) -> bool:
        """停止告警的提醒任务"""
        try:
            with transaction.atomic():
                updated_count = AlertReminderTask.objects.filter(
                    alert=alert, is_active=True
                ).update(is_active=False)

                if updated_count > 0:
                    logger.info(
                        f"停止告警 {alert.alert_id} 的 {updated_count} 个提醒任务"
                    )
                    return True
                else:
                    logger.warning(f"告警 {alert.alert_id} 没有找到活跃的提醒任务")
                    return False

        except Exception as e:
            logger.error(f"停止提醒任务失败: alert_id={alert.alert_id}, error={str(e)}")
            return False

    @classmethod
    def _update_reminder_task(
        cls, reminder: AlertReminderTask, new_frequency: int, new_max_count: int
    ) -> bool:
        """更新提醒任务配置"""
        try:
            with transaction.atomic():
                old_frequency = reminder.current_frequency_minutes
                old_max_count = reminder.current_max_reminders

                reminder.current_frequency_minutes = new_frequency
                reminder.current_max_reminders = (
                    new_max_count
                    if new_max_count >= 0
                    else cls.DEFAULT_MAX_REMINDERS
                )

                # 如果频率发生变化，需要重新计算下次提醒时间
                if old_frequency != new_frequency:
                    now = timezone.now()
                    # 如果下次提醒时间还没到，按新频率重新计算
                    if reminder.next_reminder_time > now:
                        time_since_last = (
                            now - reminder.last_reminder_time
                            if reminder.last_reminder_time
                            else timedelta(0)
                        )
                        remaining_time = (
                            timedelta(minutes=new_frequency) - time_since_last
                        )
                        if remaining_time.total_seconds() > 0:
                            reminder.next_reminder_time = now + remaining_time
                        else:
                            reminder.next_reminder_time = now

                reminder.save()

                logger.info(
                    f"更新提醒任务配置: alert_id={reminder.alert.alert_id}, "
                    f"频率: {old_frequency}->{new_frequency}分钟, "
                    f"最大次数: {old_max_count}->{new_max_count}"
                )
                return True

        except Exception as e:
            logger.error(
                f"更新提醒任务配置失败: reminder_id={reminder.id}, error={str(e)}"
            )
            return False

    @classmethod
    def check_and_process_reminders(cls) -> Dict[str, Any]:
        """检查并处理需要发送的提醒"""
        processed = 0
        success = 0
        now = timezone.now()

        try:
            # 获取需要发送提醒的任务
            pending_reminders = AlertReminderTask.objects.filter(
                is_active=True,
                next_reminder_time__lte=now,
            ).select_related("alert", "assignment")

            for reminder in pending_reminders:
                processed += 1

                try:
                    if reminder.alert.status != AlertStatus.PENDING:
                        reminder.is_active = False
                        reminder.save(update_fields=["is_active", "updated_at"])
                        logger.info(
                            "提醒任务因告警状态非待响应而停用: alert_id=%s, status=%s",
                            reminder.alert.alert_id,
                            reminder.alert.status,
                        )
                        continue

                    effective_max_reminders = cls._get_effective_max_reminders(
                        reminder
                    )

                    if (
                        effective_max_reminders > 0
                        and reminder.reminder_count >= effective_max_reminders
                    ):
                        reminder.is_active = False
                        reminder.save(update_fields=["is_active", "updated_at"])
                        logger.info(
                            "提醒任务达到最大次数，自动停用: alert_id=%s, assignment_id=%s, max_count=%s",
                            reminder.alert.alert_id,
                            reminder.assignment_id,
                            effective_max_reminders,
                        )
                        continue

                    # 发送提醒通知
                    if cls._send_reminder_notification(
                        assignment=reminder.assignment, alert=reminder.alert
                    ):
                        # 更新提醒记录
                        reminder.reminder_count += 1
                        reminder.last_reminder_time = now

                        # 计算下次提醒时间
                        if (
                            effective_max_reminders <= 0
                            or reminder.reminder_count < effective_max_reminders
                        ):
                            reminder.next_reminder_time = now + timedelta(
                                minutes=reminder.current_frequency_minutes
                            )
                        else:
                            # 达到最大次数，停止提醒
                            reminder.is_active = False

                        reminder.save()
                        success += 1

                except Exception as e:
                    logger.error(
                        f"处理提醒任务失败: reminder_id={reminder.alert.alert_id}, error={str(e)}"
                    )

        except Exception as e:
            logger.error(f"检查提醒任务失败: {str(e)}")

        return {"processed": processed, "success": success}

    @classmethod
    def _send_reminder_notification(
        cls, assignment: AlertAssignment, alert: Alert
    ) -> bool:
        """发送提醒通知"""
        try:
            if (
                alert.is_session_alert
                and alert.session_status != SessionStatus.CONFIRMED
            ):
                logger.info(
                    "提醒任务跳过会话观察期告警: alert_id=%s, session_status=%s",
                    alert.alert_id,
                    alert.session_status,
                )
                return False

            username_list = assignment.personnel
            if not username_list:
                logger.warning(
                    f"提醒任务 {assignment.id} 没有配置接收人员，无法发送通知"
                )
                return False

            channel_list = assignment.notify_channels
            if isinstance(channel_list, str):
                try:
                    channel_list = json.loads(channel_list)
                except json.JSONDecodeError:
                    logger.error(
                        f"提醒任务 {assignment.id} 的通知渠道配置错误: {channel_list}"
                    )
                    channel_list = []

            if not channel_list:
                logger.warning(
                    f"提醒任务 {assignment.id} 没有配置通知渠道，无法发送通知"
                )
                return False

            param_format = NotifyParamsFormat(
                username_list=username_list, alerts=[alert]
            )
            title = param_format.format_title()
            content = param_format.format_content()

            channel_params = []
            for channel in channel_list:
                channel_params.append(
                    {
                        "username_list": username_list,
                        "channel_type": channel["channel_type"],
                        "channel_id": channel["id"],
                        "title": title,
                        "content": content,
                        "object_id": alert.alert_id,
                        "notify_action_object": "alert",
                    }
                )
            # 移动导入到函数内部避免循环导入
            from apps.alerts.tasks import sync_notify

            # 异步发送通知
            transaction.on_commit(lambda: sync_notify.delay(channel_params))

            return True

        except Exception as e:  # noqa
            import traceback
            logger.error(f"发送提醒通知失败: reminder_id={assignment.id}, error={traceback.format_exc()}")
            return False

    @staticmethod
    def search_level_map(level_type) -> Dict[str, str]:
        instance = Level.objects.filter(level_type=level_type).values_list(
            "level_id", "level_display_name"
        )
        return {str(i[0]): i[1] for i in instance}

    @classmethod
    def cleanup_expired_reminders(cls) -> int:
        """清理过期的提醒任务记录"""
        try:
            # 清理30天前完成的提醒任务
            cutoff_time = timezone.now() - timedelta(days=30)

            deleted_count = AlertReminderTask.objects.filter(
                is_active=False, updated_at__lt=cutoff_time
            ).delete()[0]

            logger.info(f"清理了 {deleted_count} 条过期的提醒任务记录")
            return deleted_count

        except Exception as e:
            logger.error(f"清理过期提醒任务失败: {str(e)}")
            return 0
