from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.models.time_info import TimeInfo
from apps.operation_analysis.models.models import Dashboard

EXECUTION_SNAPSHOT_IMMUTABLE_ERROR = "Execution Input Snapshot 创建后不可修改"


class DashboardReportSubscription(TimeInfo):
    class Status(models.TextChoices):
        ACTIVE = "active", "启用"
        PAUSED = "paused", "暂停"
        TERMINATED = "terminated", "已终止"

    dashboard = models.ForeignKey(
        Dashboard,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="report_subscriptions",
        verbose_name="仪表盘",
    )
    creator = models.CharField(max_length=32, db_index=True, verbose_name="创建者")
    name = models.CharField(max_length=128, verbose_name="订阅名称")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
        verbose_name="状态",
    )
    recipient_email = models.EmailField(verbose_name="接收邮箱")
    config = models.JSONField(default=dict, blank=True, verbose_name="扩展配置")

    class Meta:
        db_table = "operation_analysis_dashboard_report_subscription"
        verbose_name = "仪表盘报告订阅"
        ordering = ["-id"]

    def clean(self):
        super().clean()
        if self.status == self.Status.ACTIVE and self.dashboard_id is None:
            raise ValidationError(
                {"dashboard": "启用状态的报告订阅必须关联仪表盘"}
            )

    def __str__(self):
        return self.name


class DashboardReportExecution(TimeInfo):
    class Status(models.TextChoices):
        PENDING = "pending", "等待执行"
        RUNNING = "running", "执行中"
        SUCCEEDED = "succeeded", "成功"
        FAILED = "failed", "失败"
        UNKNOWN = "unknown", "状态未知"

    class TriggerType(models.TextChoices):
        MANUAL = "manual", "手动"

    ALLOWED_TRANSITIONS = {
        Status.PENDING: {Status.RUNNING, Status.UNKNOWN},
        Status.RUNNING: {
            Status.SUCCEEDED,
            Status.FAILED,
            Status.UNKNOWN,
        },
        Status.SUCCEEDED: set(),
        Status.FAILED: set(),
        Status.UNKNOWN: set(),
    }

    subscription = models.ForeignKey(
        DashboardReportSubscription,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="executions",
        verbose_name="报告订阅",
    )
    dashboard = models.ForeignKey(
        Dashboard,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="report_executions",
        verbose_name="仪表盘",
    )
    creator = models.CharField(max_length=32, db_index=True, verbose_name="创建者")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        verbose_name="状态",
    )
    trigger_type = models.CharField(
        max_length=16,
        choices=TriggerType.choices,
        default=TriggerType.MANUAL,
        verbose_name="触发方式",
    )
    failure_stage = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="失败阶段",
    )
    error_message = models.TextField(blank=True, default="", verbose_name="错误信息")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="完成时间")

    class Meta:
        db_table = "operation_analysis_dashboard_report_execution"
        verbose_name = "仪表盘报告执行"
        ordering = ["-id"]

    def transition_to(
        self,
        target_status: str,
        *,
        failure_stage: str = "",
        error_message: str = "",
    ):
        if target_status not in self.ALLOWED_TRANSITIONS[self.status]:
            raise ValidationError(
                {"status": f"不允许从 {self.status} 转换到 {target_status}"}
            )

        now = timezone.now()
        self.status = target_status
        update_fields = ["status", "updated_at"]
        if target_status == self.Status.RUNNING:
            self.started_at = now
            update_fields.append("started_at")
        if target_status in {self.Status.SUCCEEDED, self.Status.FAILED}:
            self.finished_at = now
            update_fields.append("finished_at")
        if target_status == self.Status.FAILED:
            self.failure_stage = failure_stage
            self.error_message = error_message
            update_fields.extend(["failure_stage", "error_message"])
        self.save(update_fields=update_fields)


class DashboardReportExecutionSnapshotQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError(EXECUTION_SNAPSHOT_IMMUTABLE_ERROR)

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError(EXECUTION_SNAPSHOT_IMMUTABLE_ERROR)


class DashboardReportExecutionSnapshot(models.Model):
    execution = models.OneToOneField(
        DashboardReportExecution,
        on_delete=models.CASCADE,
        related_name="snapshot",
        verbose_name="报告执行",
    )
    dashboard_id = models.BigIntegerField(verbose_name="仪表盘 ID")
    creator_id = models.CharField(max_length=32, verbose_name="创建者 ID")
    subscription_id = models.BigIntegerField(verbose_name="报告订阅 ID")
    filter_values = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="筛选值",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="创建时间",
    )
    objects = DashboardReportExecutionSnapshotQuerySet.as_manager()

    class Meta:
        db_table = "operation_analysis_dashboard_report_execution_snapshot"
        verbose_name = "仪表盘报告执行输入快照"

    def save(self, *args, **kwargs):
        if self.pk is not None and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError(EXECUTION_SNAPSHOT_IMMUTABLE_ERROR)
        super().save(*args, **kwargs)
