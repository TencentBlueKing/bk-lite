"""治理任务模型

GovernanceTask 是统一执行记录，覆盖评估、安装、重启、验证四种任务类型。
"""

from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.patch_mgmt.constants import GovernanceTaskStatus, GovernanceTaskType, RebootPolicy


class GovernanceTask(TimeInfo, MaintainerInfo):
    """治理任务

    统一执行记录，类型包括评估、安装、重启、验证。
    一个任务使用统一的执行方式、执行窗口和重启策略。
    """

    name = models.CharField(max_length=256, verbose_name="任务名称")
    task_type = models.CharField(
        max_length=16,
        choices=GovernanceTaskType.CHOICES,
        verbose_name="任务类型",
    )
    execution_mode = models.CharField(
        max_length=16,
        default="now",
        verbose_name="执行方式",
    )
    execution_window_start = models.DateTimeField(null=True, blank=True, verbose_name="执行窗口开始")
    execution_window_end = models.DateTimeField(null=True, blank=True, verbose_name="执行窗口结束")
    auto_reboot = models.BooleanField(default=False, verbose_name="是否自动重启")
    reboot_policy = models.CharField(
        max_length=16,
        choices=RebootPolicy.CHOICES,
        default=RebootPolicy.NO_REBOOT,
        verbose_name="重启策略",
    )
    status = models.CharField(
        max_length=32,
        choices=GovernanceTaskStatus.CHOICES,
        default=GovernanceTaskStatus.PENDING,
        verbose_name="任务状态",
    )
    risk_snapshot = models.JSONField(default=list, verbose_name="风险项快照")
    target_list = models.JSONField(default=list, verbose_name="目标主机列表")
    patch_list = models.JSONField(default=list, verbose_name="补丁列表")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="完成时间")
    cancelled_by = models.CharField(max_length=32, blank=True, default="", verbose_name="取消人")
    cancelled_at = models.DateTimeField(null=True, blank=True, verbose_name="取消时间")
    cancel_reason = models.TextField(blank=True, default="", verbose_name="取消原因")
    timeout = models.IntegerField(default=3600, verbose_name="超时时间(秒)")
    team = models.JSONField(default=list, verbose_name="团队ID列表")
    parent_task = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="child_tasks",
        verbose_name="来源任务",
    )
    chain_started_at = models.DateTimeField(null=True, blank=True, verbose_name="治理链路开始时间")
    chain_deadline_at = models.DateTimeField(null=True, blank=True, verbose_name="治理链路超期时间")
    overdue_at = models.DateTimeField(null=True, blank=True, verbose_name="首次超期时间")

    class Meta:
        db_table = "patch_governance_task"
        verbose_name = "治理任务"
        verbose_name_plural = verbose_name
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.task_type})"


class GovernanceTaskHost(TimeInfo):
    """治理任务主机级结果

    每台主机在每个治理任务中的执行阶段、结果和日志。
    """

    task = models.ForeignKey(
        GovernanceTask,
        on_delete=models.CASCADE,
        related_name="host_results",
        verbose_name="所属任务",
    )
    target_id = models.BigIntegerField(verbose_name="目标主机ID")
    target_name = models.CharField(max_length=128, blank=True, default="", verbose_name="主机名")
    target_ip = models.CharField(max_length=64, blank=True, default="", verbose_name="主机IP")
    stage = models.CharField(max_length=64, default="waiting", verbose_name="当前阶段")
    stage_color = models.CharField(max_length=32, default="default", verbose_name="阶段颜色")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="实际开始时间")
    exit_code = models.IntegerField(null=True, blank=True, verbose_name="退出码")
    failed_stage = models.CharField(max_length=64, blank=True, default="", verbose_name="失败阶段")
    error_code = models.CharField(max_length=128, blank=True, default="", verbose_name="错误码")
    reason = models.TextField(blank=True, default="", verbose_name="失败原因")
    suggestion = models.TextField(blank=True, default="", verbose_name="处理建议")
    can_retry = models.BooleanField(default=False, verbose_name="是否可重试")
    log = models.TextField(blank=True, default="", verbose_name="执行日志")
    stage_started_at = models.DateTimeField(null=True, blank=True, verbose_name="当前阶段开始时间")
    stage_deadline_at = models.DateTimeField(null=True, blank=True, verbose_name="当前阶段截止时间")
    last_heartbeat_at = models.DateTimeField(null=True, blank=True, verbose_name="最近心跳时间")
    reconcile_deadline_at = models.DateTimeField(null=True, blank=True, verbose_name="结果核验截止时间")
    reconcile_attempts = models.PositiveIntegerField(default=0, verbose_name="结果核验次数")
    boot_marker_before = models.CharField(max_length=128, blank=True, default="", verbose_name="重启前启动标识")
    timeout_reason = models.TextField(blank=True, default="", verbose_name="超时原因")

    class Meta:
        db_table = "patch_governance_task_host"
        verbose_name = "治理任务主机结果"
        verbose_name_plural = verbose_name
        unique_together = (("task", "target_id"),)

    def __str__(self):
        return f"{self.task.name} - {self.target_name}"
