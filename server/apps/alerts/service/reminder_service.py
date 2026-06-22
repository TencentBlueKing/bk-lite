# -- coding: utf-8 --
# @File: reminder_service.py
# @Time: 2025/6/11 10:00
# @Author: windyzhao
import json

from django.utils import timezone
from django.db import transaction, connection
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
                    logger.warning("[AlertReminder] 告警 %s 已存在活跃的提醒任务", alert.alert_id)
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
                "[AlertReminder] 为告警 %s 创建提醒任务，频率: %s分钟，最大次数: %s",
                alert.alert_id, interval_minutes, max_count,
            )
            return reminder_task

        except Exception as e:
            logger.error("[AlertReminder] 创建提醒任务失败: alert_id=%s, error=%s", alert.alert_id, e, exc_info=True)
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
                        "[AlertReminder] 停止告警 %s 的 %s 个提醒任务",
                        alert.alert_id, updated_count,
                    )
                    return True
                else:
                    logger.warning("[AlertReminder] 告警 %s 没有找到活跃的提醒任务", alert.alert_id)
                    return False

        except Exception as e:
            logger.error("[AlertReminder] 停止提醒任务失败: alert_id=%s, error=%s", alert.alert_id, e, exc_info=True)
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
                    "[AlertReminder] 更新提醒任务配置: alert_id=%s, 频率: %s->%s分钟, 最大次数: %s->%s",
                    reminder.alert.alert_id, old_frequency, new_frequency, old_max_count, new_max_count,
                )
                return True

        except Exception as e:
            logger.error(
                "[AlertReminder] 更新提醒任务配置失败: reminder_id=%s, error=%s",
                reminder.id, e, exc_info=True,
            )
            return False

    @classmethod
    def check_and_process_reminders(cls) -> Dict[str, Any]:
        """检查并处理需要发送的提醒"""
        processed = 0
        success = 0

        try:
            pending_reminder_ids = list(
                AlertReminderTask.objects.filter(
                    is_active=True,
                    next_reminder_time__lte=timezone.now(),
                ).values_list("id", flat=True)
            )

            select_for_update_kwargs = {}
            if connection.features.has_select_for_update_skip_locked:
                select_for_update_kwargs["skip_locked"] = True

            for reminder_id in pending_reminder_ids:
                try:
                    with transaction.atomic():
                        reminder = (
                            AlertReminderTask.objects.select_for_update(
                                **select_for_update_kwargs
                            )
                            .select_related("alert", "assignment")
                            .filter(id=reminder_id, is_active=True)
                            .first()
                        )

                        if not reminder:
                            continue

                        if reminder.next_reminder_time > timezone.now():
                            continue

                        processed += 1

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

                        if cls._send_reminder_notification(
                            assignment=reminder.assignment,
                            alert=reminder.alert,
                            reminder_id=reminder.id,
                        ):
                            success += 1

                except Exception as e:
                    logger.error(
                        "处理提醒任务失败: reminder_id=%s, error=%s",
                        reminder_id,
                        str(e),
                    )

        except Exception as e:
            logger.error("[AlertReminder] 检查提醒任务失败: %s", e, exc_info=True)

        return {"processed": processed, "success": success}

    @classmethod
    def _send_reminder_notification(
        cls,
        assignment: AlertAssignment,
        alert: Alert,
        reminder_id: Optional[int] = None,
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

            from apps.alerts.service.escalation_service import EscalationService

            roster, layer_channels = EscalationService.active_roster_for_reminder(alert)
            username_list = roster if roster is not None else assignment.personnel
            if not username_list:
                logger.warning(
                    "[AlertReminder] 提醒任务 %s 没有配置接收人员，无法发送通知",
                    assignment.id,
                )
                return False

            channel_list = layer_channels if layer_channels else assignment.notify_channels
            if isinstance(channel_list, str):
                try:
                    channel_list = json.loads(channel_list)
                except json.JSONDecodeError:
                    logger.error(
                        "[AlertReminder] 提醒任务 %s 的通知渠道配置错误: %s",
                        assignment.id, channel_list,
                    )
                    channel_list = []

            if not channel_list:
                logger.warning(
                    "[AlertReminder] 提醒任务 %s 没有配置通知渠道，无法发送通知",
                    assignment.id,
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

            def enqueue_and_mark() -> bool:
                try:
                    sync_notify.delay(channel_params)
                    if reminder_id is not None:
                        return cls._advance_reminder_after_enqueue(reminder_id)
                    return True
                except Exception:
                    logger.exception(
                        "提醒通知任务投递失败: reminder_id=%s, assignment_id=%s, alert_id=%s",
                        reminder_id,
                        assignment.id,
                        alert.alert_id,
                    )
                    return False

            # 有外层事务时，提交后再投递，并仅在入队成功后推进提醒状态
            if transaction.get_connection().in_atomic_block:
                transaction.on_commit(enqueue_and_mark)
                return True

            return enqueue_and_mark()

        except Exception:  # noqa
            logger.error(
                "发送提醒通知失败: reminder_id=%s, assignment_id=%s, alert_id=%s",
                reminder_id,
                assignment.id,
                alert.alert_id,
                exc_info=True,
            )
            return False

    @classmethod
    def _advance_reminder_after_enqueue(cls, reminder_id: int) -> bool:
        """仅在通知任务成功入队后推进提醒状态。"""
        try:
            with transaction.atomic():
                reminder = (
                    AlertReminderTask.objects.select_for_update()
                    .select_related("alert", "assignment")
                    .filter(id=reminder_id)
                    .first()
                )

                if not reminder:
                    logger.warning("提醒任务不存在，无法推进状态: reminder_id=%s", reminder_id)
                    return False

                if not reminder.is_active:
                    logger.info("提醒任务已停用，跳过状态推进: reminder_id=%s", reminder_id)
                    return True

                if reminder.alert.status != AlertStatus.PENDING:
                    reminder.is_active = False
                    reminder.save(update_fields=["is_active", "updated_at"])
                    logger.info(
                        "提醒任务入队后因告警状态非待响应而停用: alert_id=%s, status=%s",
                        reminder.alert.alert_id,
                        reminder.alert.status,
                    )
                    return True

                effective_max_reminders = cls._get_effective_max_reminders(reminder)
                if (
                    effective_max_reminders > 0
                    and reminder.reminder_count >= effective_max_reminders
                ):
                    reminder.is_active = False
                    reminder.save(update_fields=["is_active", "updated_at"])
                    logger.info(
                        "提醒任务入队后发现已达到最大次数，自动停用: alert_id=%s, assignment_id=%s, max_count=%s",
                        reminder.alert.alert_id,
                        reminder.assignment_id,
                        effective_max_reminders,
                    )
                    return True

                now = timezone.now()
                reminder.reminder_count += 1
                reminder.last_reminder_time = now
                update_fields = ["reminder_count", "last_reminder_time", "updated_at"]

                if (
                    effective_max_reminders <= 0
                    or reminder.reminder_count < effective_max_reminders
                ):
                    reminder.next_reminder_time = now + timedelta(
                        minutes=reminder.current_frequency_minutes
                    )
                    update_fields.append("next_reminder_time")
                else:
                    reminder.is_active = False
                    update_fields.append("is_active")

                reminder.save(update_fields=update_fields)
                return True

        except Exception:
            logger.error(
                "推进提醒状态失败: reminder_id=%s",
                reminder_id,
                exc_info=True,
            )
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

            logger.info("[AlertReminder] 清理了 %s 条过期的提醒任务记录", deleted_count)
            return deleted_count

        except Exception as e:
            logger.error("[AlertReminder] 清理过期提醒任务失败: %s", e, exc_info=True)
            return 0
