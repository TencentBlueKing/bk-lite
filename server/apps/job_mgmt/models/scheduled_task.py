"""定时任务模型"""

from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.job_mgmt.constants import ConcurrencyPolicy, JobType, ScheduleType, ScriptType
from apps.job_mgmt.models.playbook import Playbook
from apps.job_mgmt.models.script import Script
from apps.job_mgmt.models.target import Target


class ScheduledTask(TimeInfo, MaintainerInfo):
    """
    定时任务

    支持单次执行和周期执行（Cron）
    """

    name = models.CharField(max_length=128, verbose_name="任务名称")
    description = models.TextField(blank=True, default="", verbose_name="描述")

    job_type = models.CharField(max_length=32, choices=JobType.CHOICES, verbose_name="作业类型")
    schedule_type = models.CharField(max_length=32, choices=ScheduleType.CHOICES, default=ScheduleType.ONCE, verbose_name="调度类型")

    # Cron 表达式（schedule_type=cron 时使用）
    cron_expression = models.CharField(max_length=128, blank=True, default="", verbose_name="Cron表达式")

    # 单次执行时间（schedule_type=once 时使用）
    scheduled_time = models.DateTimeField(null=True, blank=True, verbose_name="计划执行时间")

    # 关联的脚本/Playbook
    script = models.ForeignKey(Script, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="关联脚本")
    playbook = models.ForeignKey(Playbook, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="关联Playbook")

    # 执行目标
    targets = models.ManyToManyField(Target, verbose_name="执行目标")

    # 执行参数
    params = models.JSONField(default=dict, verbose_name="执行参数")

    # 脚本执行专用字段（快速执行场景）
    script_type = models.CharField(max_length=32, choices=ScriptType.CHOICES, blank=True, default="", verbose_name="脚本类型")
    script_content = models.TextField(blank=True, default="", verbose_name="脚本内容")

    # 文件分发专用字段
    files = models.JSONField(default=list, verbose_name="分发文件列表")
    target_path = models.CharField(max_length=512, blank=True, default="", verbose_name="目标路径")

    # 超时设置
    timeout = models.IntegerField(default=300, verbose_name="超时时间")

    # 并发策略
    concurrency_policy = models.CharField(max_length=32, choices=ConcurrencyPolicy.CHOICES, default=ConcurrencyPolicy.SKIP, verbose_name="并发策略")

    # 任务状态
    is_enabled = models.BooleanField(default=True, verbose_name="是否启用")

    # celery-beat 任务ID（用于关联 PeriodicTask）
    periodic_task_id = models.IntegerField(null=True, blank=True, verbose_name="周期任务ID")

    # 执行统计
    last_run_at = models.DateTimeField(null=True, blank=True, verbose_name="上次执行时间")
    run_count = models.IntegerField(default=0, verbose_name="执行次数")

    # 组织归属
    team = models.JSONField(default=list, verbose_name="团队ID列表")

    class Meta:
        verbose_name = "定时任务"
        verbose_name_plural = verbose_name
        db_table = "job_scheduled_task"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name
