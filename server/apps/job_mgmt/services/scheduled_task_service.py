"""定时任务 Celery Beat 集成服务"""

import json
from typing import Optional

from django_celery_beat.models import ClockedSchedule, CrontabSchedule, PeriodicTask

from apps.core.logger import job_logger as logger
from apps.job_mgmt.constants import ScheduleType


class ScheduledTaskService:
    """定时任务服务 - 管理 Celery Beat PeriodicTask"""

    # Celery Task 路径
    TASK_PATH = "apps.job_mgmt.tasks.execute_scheduled_task"

    # PeriodicTask 名称前缀
    TASK_NAME_PREFIX = "job_mgmt_scheduled_task_"

    @classmethod
    def get_periodic_task_name(cls, scheduled_task_id: int) -> str:
        """生成 PeriodicTask 名称"""
        return f"{cls.TASK_NAME_PREFIX}{scheduled_task_id}"

    @classmethod
    def create_periodic_task(cls, scheduled_task) -> Optional[PeriodicTask]:
        """
        创建 PeriodicTask

        Args:
            scheduled_task: ScheduledTask 实例

        Returns:
            创建的 PeriodicTask 实例，如果不需要创建则返回 None
        """
        task_name = cls.get_periodic_task_name(scheduled_task.id)

        if scheduled_task.schedule_type == ScheduleType.CRON:
            # 周期执行：使用 CrontabSchedule
            return cls._create_cron_task(scheduled_task, task_name)
        elif scheduled_task.schedule_type == ScheduleType.ONCE:
            # 单次执行：使用 ClockedSchedule
            return cls._create_once_task(scheduled_task, task_name)
        else:
            logger.warning(f"未知的调度类型: {scheduled_task.schedule_type}")
            return None

    @classmethod
    def _create_cron_task(cls, scheduled_task, task_name: str) -> Optional[PeriodicTask]:
        """创建 Cron 周期任务"""
        cron_expression = scheduled_task.cron_expression
        if not cron_expression:
            logger.warning(f"定时任务 {scheduled_task.id} 未设置 Cron 表达式")
            return None

        try:
            # 解析 Cron 表达式 (minute hour day_of_month month_of_year day_of_week)
            parts = cron_expression.strip().split()
            if len(parts) != 5:
                logger.error(f"无效的 Cron 表达式: {cron_expression}")
                return None

            minute, hour, day_of_month, month_of_year, day_of_week = parts

            # 获取或创建 CrontabSchedule
            schedule, _ = CrontabSchedule.objects.get_or_create(
                minute=minute,
                hour=hour,
                day_of_month=day_of_month,
                month_of_year=month_of_year,
                day_of_week=day_of_week,
            )

            # 创建或更新 PeriodicTask
            periodic_task, created = PeriodicTask.objects.update_or_create(
                name=task_name,
                defaults={
                    "task": cls.TASK_PATH,
                    "crontab": schedule,
                    "clocked": None,
                    "args": json.dumps([scheduled_task.id]),
                    "kwargs": json.dumps({}),
                    "enabled": scheduled_task.is_enabled,
                    "one_off": False,
                },
            )

            action = "创建" if created else "更新"
            logger.info(f"{action} Cron 周期任务: {task_name}")

            return periodic_task

        except Exception as e:
            logger.exception(f"创建 Cron 任务失败: {e}")
            return None

    @classmethod
    def _create_once_task(cls, scheduled_task, task_name: str) -> Optional[PeriodicTask]:
        """创建单次执行任务"""
        scheduled_time = scheduled_task.scheduled_time
        if not scheduled_time:
            logger.warning(f"定时任务 {scheduled_task.id} 未设置计划执行时间")
            return None

        try:
            # 获取或创建 ClockedSchedule
            schedule, _ = ClockedSchedule.objects.get_or_create(
                clocked_time=scheduled_time,
            )

            # 创建或更新 PeriodicTask
            periodic_task, created = PeriodicTask.objects.update_or_create(
                name=task_name,
                defaults={
                    "task": cls.TASK_PATH,
                    "clocked": schedule,
                    "crontab": None,
                    "args": json.dumps([scheduled_task.id]),
                    "kwargs": json.dumps({}),
                    "enabled": scheduled_task.is_enabled,
                    "one_off": True,  # 单次执行
                },
            )

            action = "创建" if created else "更新"
            logger.info(f"{action}单次执行任务: {task_name}")

            return periodic_task

        except Exception as e:
            logger.exception(f"创建单次执行任务失败: {e}")
            return None

    @classmethod
    def update_periodic_task(cls, scheduled_task) -> Optional[PeriodicTask]:
        """
        更新 PeriodicTask

        Args:
            scheduled_task: ScheduledTask 实例

        Returns:
            更新后的 PeriodicTask 实例
        """
        # 先删除旧的，再创建新的（简化处理调度类型变更的情况）
        cls.delete_periodic_task(scheduled_task.id)
        return cls.create_periodic_task(scheduled_task)

    @classmethod
    def delete_periodic_task(cls, scheduled_task_id: int) -> bool:
        """
        删除 PeriodicTask

        Args:
            scheduled_task_id: ScheduledTask ID

        Returns:
            是否删除成功
        """
        task_name = cls.get_periodic_task_name(scheduled_task_id)

        try:
            deleted_count, _ = PeriodicTask.objects.filter(name=task_name).delete()
            if deleted_count > 0:
                logger.info(f"删除周期任务: {task_name}")
                return True
            else:
                logger.debug(f"未找到要删除的周期任务: {task_name}")
                return False
        except Exception as e:
            logger.exception(f"删除周期任务失败: {task_name}, 错误: {e}")
            return False

    @classmethod
    def toggle_periodic_task(cls, scheduled_task_id: int, enabled: bool) -> bool:
        """
        启用/禁用 PeriodicTask

        Args:
            scheduled_task_id: ScheduledTask ID
            enabled: 是否启用

        Returns:
            是否操作成功
        """
        task_name = cls.get_periodic_task_name(scheduled_task_id)

        try:
            updated_count = PeriodicTask.objects.filter(name=task_name).update(enabled=enabled)
            if updated_count > 0:
                action = "启用" if enabled else "禁用"
                logger.info(f"{action}周期任务: {task_name}")
                return True
            else:
                logger.warning(f"未找到要操作的周期任务: {task_name}")
                return False
        except Exception as e:
            logger.exception(f"切换周期任务状态失败: {task_name}, 错误: {e}")
            return False

    @classmethod
    def sync_periodic_task(cls, scheduled_task) -> Optional[int]:
        """
        同步 PeriodicTask 并返回其 ID

        如果 PeriodicTask 不存在则创建，存在则更新

        Args:
            scheduled_task: ScheduledTask 实例

        Returns:
            PeriodicTask ID，如果失败则返回 None
        """
        periodic_task = cls.create_periodic_task(scheduled_task)
        if periodic_task:
            return periodic_task.id
        return None
