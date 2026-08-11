from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models.expressions import BaseExpression

from apps.core.models.time_info import TimeInfo
from apps.operation_analysis.models.models import Dashboard
from apps.system_mgmt.models import Channel

EXECUTION_SNAPSHOT_IMMUTABLE_ERROR = "Execution Input Snapshot 创建后不可修改"
RENDER_SNAPSHOT_IMMUTABLE_ERROR = "Render Snapshot 创建后不可修改"
_RESOURCE_TYPE_DASHBOARD = "dashboard"
_DEFAULT_RENDER_SCHEMA_VERSION = 1


def _sync_dashboard_resource_fields(instance) -> None:
    """ORM 兼容：仅有 dashboard FK 时回填 resource_*（测试与内部创建）。"""
    if instance.dashboard_id is None or instance.resource_id is not None:
        return
    if not instance.resource_type:
        instance.resource_type = _RESOURCE_TYPE_DASHBOARD
    if instance.resource_type == _RESOURCE_TYPE_DASHBOARD:
        instance.resource_id = instance.dashboard_id


class AliveSubscriptionManager(models.Manager):
    """默认排除逻辑删除的 Subscription；审计/生命周期用 all_objects。"""

    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class DashboardReportSubscription(TimeInfo):
    class Status(models.TextChoices):
        ACTIVE = "active", "启用"
        PAUSED = "paused", "暂停"
        TERMINATED = "terminated", "已终止"

    class ScheduleType(models.TextChoices):
        DAILY = "daily", "每天"
        WEEKLY = "weekly", "每周"
        MONTHLY = "monthly", "每月"

    class LifecycleAction(models.TextChoices):
        PAUSE = "pause", "暂停"
        RESUME = "resume", "恢复"

    dashboard = models.ForeignKey(
        Dashboard,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="report_subscriptions",
        verbose_name="仪表盘",
    )
    resource_type = models.CharField(
        max_length=32,
        default=_RESOURCE_TYPE_DASHBOARD,
        db_index=True,
        verbose_name="画布资源类型",
    )
    resource_id = models.BigIntegerField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="画布资源 ID",
    )
    creator = models.CharField(max_length=100, db_index=True, verbose_name="创建者")
    creator_domain = models.CharField(
        max_length=100,
        default="domain.com",
        db_index=True,
        verbose_name="创建者域",
    )
    team_id = models.BigIntegerField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="订阅所属组织 ID",
    )
    name = models.CharField(max_length=128, verbose_name="订阅名称")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
        verbose_name="状态",
    )
    recipient_email = models.EmailField(verbose_name="接收邮箱")
    email_channel = models.ForeignKey(
        Channel,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="report_subscriptions",
        verbose_name="邮件通道",
    )
    schedule_type = models.CharField(
        max_length=16,
        choices=ScheduleType.choices,
        null=True,
        blank=True,
        verbose_name="周期类型",
    )
    schedule_hour = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="计划小时",
    )
    schedule_minute = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="计划分钟",
    )
    schedule_weekday = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="计划星期（0=周一）",
    )
    schedule_day_of_month = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="计划日（1–31）",
    )
    timezone = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        verbose_name="订阅时区",
    )
    next_run_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="下次计划执行时间",
    )
    version = models.PositiveIntegerField(
        default=1,
        verbose_name="调度配置版本",
    )
    revision = models.PositiveIntegerField(
        default=1,
        verbose_name="订阅并发修订号",
    )
    config = models.JSONField(default=dict, blank=True, verbose_name="扩展配置")
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="逻辑删除时间",
    )
    deleted_by = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="逻辑删除操作者",
    )
    deleted_by_domain = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="逻辑删除操作者域",
    )
    terminated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="终止时间",
    )
    terminated_by = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="终止操作者",
    )
    terminated_by_domain = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="终止操作者域",
    )
    termination_reason = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="终止原因",
    )
    last_lifecycle_action = models.CharField(
        max_length=16,
        blank=True,
        default="",
        choices=LifecycleAction.choices,
        verbose_name="最近生命周期操作",
    )
    last_lifecycle_actor = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="最近生命周期操作者",
    )
    last_lifecycle_actor_domain = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="最近生命周期操作者域",
    )
    last_lifecycle_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="最近生命周期操作时间",
    )

    objects = AliveSubscriptionManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "operation_analysis_dashboard_report_subscription"
        verbose_name = "仪表盘报告订阅"
        ordering = ["-id"]
        indexes = [
            models.Index(
                fields=["creator", "creator_domain"],
                name="idx_drs_creator_identity",
            ),
            models.Index(
                fields=["status", "next_run_at"],
                name="idx_drs_status_next_run",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.status == self.Status.ACTIVE:
            if self.resource_id is None:
                errors["resource_id"] = "启用状态的报告订阅必须关联画布资源"
            if self.resource_type == _RESOURCE_TYPE_DASHBOARD and self.dashboard_id is None:
                errors["dashboard"] = "启用状态的报告订阅必须关联仪表盘"
        if self.schedule_type is not None:
            if self.schedule_hour is None or not (0 <= self.schedule_hour <= 23):
                errors["schedule_hour"] = "已配置调度时必须指定 0–23 小时"
            if self.schedule_minute is None or not (0 <= self.schedule_minute <= 59):
                errors["schedule_minute"] = "已配置调度时必须指定 0–59 分钟"
            if not self.timezone:
                errors["timezone"] = "已配置调度时必须指定 IANA 时区"
            if self.schedule_type == self.ScheduleType.WEEKLY and (self.schedule_weekday is None or not (0 <= self.schedule_weekday <= 6)):
                errors["schedule_weekday"] = "每周调度必须指定 weekday（0–6）"
            if self.schedule_type == self.ScheduleType.MONTHLY and (
                self.schedule_day_of_month is None or not (1 <= self.schedule_day_of_month <= 31)
            ):
                errors["schedule_day_of_month"] = "每月调度必须指定 day_of_month（1–31）"
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        _sync_dashboard_resource_fields(self)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class DashboardReportExecutionQuerySet(models.QuerySet):
    GUARDED_FIELDS = {"request_id", "trigger_type", "scheduled_time_utc"}

    def update(self, **kwargs):
        if "request_guard" in kwargs and "request_id" not in kwargs:
            raise ValueError("request_guard 是派生保护字段，不能单独更新")
        if "scheduled_guard" in kwargs and not {"trigger_type", "scheduled_time_utc"}.intersection(kwargs):
            raise ValueError("scheduled_guard 是派生保护字段，不能单独更新")
        protected_updates = self.GUARDED_FIELDS.intersection(kwargs)
        if "request_id" in protected_updates:
            request_id = kwargs["request_id"]
            if isinstance(request_id, BaseExpression):
                raise ValueError("request_id 表达式更新无法安全推导 request_guard")
            kwargs["request_guard"] = True if request_id else None
        schedule_updates = {"trigger_type", "scheduled_time_utc"}.intersection(protected_updates)
        if schedule_updates:
            if schedule_updates != {"trigger_type", "scheduled_time_utc"}:
                raise ValueError("trigger_type 与 scheduled_time_utc 必须通过 save 或在同一次 update 中更新")
            trigger_type = kwargs["trigger_type"]
            scheduled_time_utc = kwargs["scheduled_time_utc"]
            if isinstance(trigger_type, BaseExpression) or isinstance(scheduled_time_utc, BaseExpression):
                raise ValueError("计划执行字段的表达式更新无法安全推导 scheduled_guard")
            kwargs["scheduled_guard"] = (
                True if trigger_type == DashboardReportExecution.TriggerType.SCHEDULED and scheduled_time_utc is not None else None
            )
        return super().update(**kwargs)

    def bulk_create(self, objs, *args, **kwargs):
        objs = list(objs)
        for obj in objs:
            self._sync_guards(obj)
        return super().bulk_create(objs, *args, **kwargs)

    def bulk_update(self, objs, fields, *args, **kwargs):
        objs = list(objs)
        fields = list(fields)
        if "request_guard" in fields and "request_id" not in fields:
            raise ValueError("request_guard 是派生保护字段，不能单独更新")
        if "scheduled_guard" in fields and not {"trigger_type", "scheduled_time_utc"}.intersection(fields):
            raise ValueError("scheduled_guard 是派生保护字段，不能单独更新")
        guarded_update = bool(self.GUARDED_FIELDS.intersection(fields))
        if "request_id" in fields and "request_guard" not in fields:
            fields.append("request_guard")
        if {"trigger_type", "scheduled_time_utc"}.intersection(fields) and "scheduled_guard" not in fields:
            fields.append("scheduled_guard")
        for obj in objs:
            self._sync_guards(obj)
        if guarded_update:
            with transaction.atomic(using=self.db):
                for obj in objs:
                    obj.save(update_fields=fields, using=self.db)
            return len(objs)
        return super().bulk_update(objs, fields, *args, **kwargs)

    @staticmethod
    def _sync_guards(obj):
        obj.request_guard = True if obj.request_id else None
        obj.scheduled_guard = (
            True if obj.trigger_type == DashboardReportExecution.TriggerType.SCHEDULED and obj.scheduled_time_utc is not None else None
        )


class DashboardReportExecution(TimeInfo):
    class Status(models.TextChoices):
        PENDING = "pending", "等待执行"
        RUNNING = "running", "执行中"
        SUCCEEDED = "succeeded", "成功"
        FAILED = "failed", "失败"
        UNKNOWN = "unknown", "状态未知"

    class TriggerType(models.TextChoices):
        MANUAL_TEST = "manual_test", "手动测试"
        SCHEDULED = "scheduled", "计划执行"

    ALLOWED_TRANSITIONS = {
        # pending → running 只能走 claim_execution，不在 transition() 允许集内
        Status.PENDING: {Status.FAILED, Status.UNKNOWN},
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
    resource_type = models.CharField(
        max_length=32,
        default=_RESOURCE_TYPE_DASHBOARD,
        db_index=True,
        verbose_name="画布资源类型",
    )
    resource_id = models.BigIntegerField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="画布资源 ID",
    )
    creator = models.CharField(max_length=100, db_index=True, verbose_name="创建者")
    creator_domain = models.CharField(
        max_length=100,
        default="domain.com",
        db_index=True,
        verbose_name="创建者域",
    )
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
        default=TriggerType.MANUAL_TEST,
        verbose_name="触发方式",
    )
    request_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="请求幂等键",
    )
    scheduled_time_utc = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="计划执行时间 UTC",
    )
    failure_stage = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="失败阶段",
    )
    error_code = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="稳定错误码",
    )
    error_message = models.TextField(blank=True, default="", verbose_name="错误信息")
    attempt_count = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="已开始 Attempt 数",
    )
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="完成时间")
    delivered_at = models.DateTimeField(null=True, blank=True, verbose_name="投递时间")

    class DeliveryOutcome(models.TextChoices):
        NOT_DELIVERED = "not_delivered", "未确认投递"
        DELIVERED = "delivered", "已确认投递"
        SMTP_UNKNOWN = "smtp_unknown", "SMTP 结果未知"

    delivery_outcome = models.CharField(
        max_length=16,
        choices=DeliveryOutcome.choices,
        default=DeliveryOutcome.NOT_DELIVERED,
        db_index=True,
        verbose_name="投递事实",
    )
    reconciled_from_status = models.CharField(
        max_length=16,
        blank=True,
        default="",
        verbose_name="Delivery Fact 仲裁前状态",
    )
    reconciliation_reason = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="Delivery Fact 仲裁原因",
    )
    reconciliation_source = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="Delivery Fact 仲裁来源",
    )
    reconciled_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Delivery Fact 仲裁时间",
    )
    source_canvas_deleted_during_execution = models.BooleanField(
        default=False,
        verbose_name="执行期间源画布被删除",
    )
    request_guard = models.BooleanField(null=True, default=None, editable=False)
    scheduled_guard = models.BooleanField(null=True, default=None, editable=False)

    objects = DashboardReportExecutionQuerySet.as_manager()

    class Meta:
        db_table = "operation_analysis_dashboard_report_execution"
        verbose_name = "仪表盘报告执行"
        ordering = ["-id"]
        indexes = [
            models.Index(
                fields=["creator", "creator_domain"],
                name="idx_dre_creator_identity",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "request_id", "trigger_type"],
                condition=~models.Q(request_id=""),
                name="uniq_dashboard_report_execution_request",
            ),
            models.UniqueConstraint(
                fields=["subscription", "scheduled_time_utc", "trigger_type"],
                condition=models.Q(
                    trigger_type="scheduled",
                    scheduled_time_utc__isnull=False,
                ),
                name="uniq_dashboard_report_execution_scheduled",
            ),
            models.UniqueConstraint(
                fields=["subscription", "request_id", "trigger_type", "request_guard"],
                name="uniq_dashboard_report_execution_request_guard",
            ),
            models.UniqueConstraint(
                fields=["subscription", "scheduled_time_utc", "trigger_type", "scheduled_guard"],
                name="uniq_dashboard_report_execution_scheduled_guard",
            ),
        ]

    def save(self, *args, **kwargs):
        _sync_dashboard_resource_fields(self)
        self.request_guard = True if self.request_id else None
        self.scheduled_guard = True if self.trigger_type == self.TriggerType.SCHEDULED and self.scheduled_time_utc is not None else None
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            update_fields = set(update_fields)
            if "request_id" in update_fields:
                update_fields.add("request_guard")
            if {"trigger_type", "scheduled_time_utc"}.intersection(update_fields):
                update_fields.add("scheduled_guard")
            kwargs["update_fields"] = update_fields
        super().save(*args, **kwargs)


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
    dashboard_id = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="仪表盘 ID",
    )
    resource_type = models.CharField(
        max_length=32,
        default=_RESOURCE_TYPE_DASHBOARD,
        verbose_name="画布资源类型",
    )
    resource_id = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="画布资源 ID",
    )
    resource_display_label = models.CharField(
        max_length=32,
        default="仪表盘",
        verbose_name="画布类型展示标签",
    )
    creator_id = models.CharField(max_length=100, verbose_name="创建者 ID")
    creator_domain = models.CharField(
        max_length=100,
        default="domain.com",
        verbose_name="创建者域",
    )
    creator_timezone = models.CharField(
        max_length=64,
        default="Asia/Shanghai",
        verbose_name="创建者时区",
    )
    subscription_id = models.BigIntegerField(verbose_name="报告订阅 ID")
    subscription_name = models.CharField(
        max_length=128,
        default="",
        verbose_name="订阅名称",
    )
    recipient_email = models.EmailField(
        default="",
        verbose_name="接收邮箱",
    )
    trigger_type = models.CharField(
        max_length=16,
        default="",
        verbose_name="触发方式",
    )
    email_channel_id = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="邮件通道 ID",
    )
    execution_team_id = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="执行组织 ID",
    )
    scheduled_time_utc = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="计划执行时间 UTC",
    )
    schedule_timezone = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="订阅计划时区",
    )
    scheduled_local_time = models.CharField(
        max_length=32,
        blank=True,
        default="",
        verbose_name="本地计划时间（展示/审计）",
    )
    subscription_version = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="调度配置版本",
    )
    subscription_revision = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="订阅修订号",
    )
    filter_values = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="筛选值",
    )
    filter_semantics = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="筛选语义（未解析）",
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
        if self.resource_id is None and self.dashboard_id is not None:
            if not self.resource_type:
                self.resource_type = _RESOURCE_TYPE_DASHBOARD
            if self.resource_type == _RESOURCE_TYPE_DASHBOARD:
                self.resource_id = self.dashboard_id
        super().save(*args, **kwargs)


class DashboardReportRenderSnapshotQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError(RENDER_SNAPSHOT_IMMUTABLE_ERROR)

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError(RENDER_SNAPSHOT_IMMUTABLE_ERROR)


class DashboardReportRenderSnapshot(models.Model):
    execution = models.OneToOneField(
        DashboardReportExecution,
        on_delete=models.CASCADE,
        related_name="render_snapshot",
        verbose_name="报告执行",
    )
    dashboard_id = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="仪表盘 ID",
    )
    dashboard_name = models.CharField(max_length=128, verbose_name="仪表盘名称")
    dashboard_updated_at = models.DateTimeField(verbose_name="仪表盘更新时间")
    resource_type = models.CharField(
        max_length=32,
        default=_RESOURCE_TYPE_DASHBOARD,
        verbose_name="画布资源类型",
    )
    resource_id = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="画布资源 ID",
    )
    resource_display_label = models.CharField(
        max_length=32,
        default="仪表盘",
        verbose_name="画布类型展示标签",
    )
    render_schema_version = models.PositiveIntegerField(
        default=_DEFAULT_RENDER_SCHEMA_VERSION,
        verbose_name="渲染快照 schema 版本",
    )
    view_sets = models.JSONField(default=list, verbose_name="仪表盘布局")
    filters = models.JSONField(null=True, blank=True, verbose_name="筛选配置")
    other = models.JSONField(null=True, blank=True, verbose_name="其他配置")
    widget_manifest = models.JSONField(
        default=list,
        verbose_name="Widget 清单",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="创建时间",
    )
    objects = DashboardReportRenderSnapshotQuerySet.as_manager()

    class Meta:
        db_table = "operation_analysis_dashboard_report_render_snapshot"
        verbose_name = "仪表盘报告渲染快照"

    def save(self, *args, **kwargs):
        if self.pk is not None and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError(RENDER_SNAPSHOT_IMMUTABLE_ERROR)
        if self.resource_id is None and self.dashboard_id is not None:
            if not self.resource_type:
                self.resource_type = _RESOURCE_TYPE_DASHBOARD
            if self.resource_type == _RESOURCE_TYPE_DASHBOARD:
                self.resource_id = self.dashboard_id
        super().save(*args, **kwargs)


class DashboardReportPdfArtifact(models.Model):
    execution = models.OneToOneField(
        DashboardReportExecution,
        on_delete=models.CASCADE,
        related_name="pdf_artifact",
        verbose_name="报告执行",
    )
    storage_reference = models.CharField(
        max_length=255,
        verbose_name="临时存储引用",
    )
    filename = models.CharField(max_length=255, verbose_name="附件文件名")
    size_bytes = models.BigIntegerField(verbose_name="文件大小")
    sha256 = models.CharField(max_length=64, verbose_name="内容 SHA-256")
    expires_at = models.DateTimeField(
        db_index=True,
        verbose_name="临时文件到期时间",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="生成时间",
    )

    class Meta:
        db_table = "operation_analysis_dashboard_report_pdf_artifact"
        verbose_name = "仪表盘报告 PDF 临时产物"


class DashboardReportRenderToken(models.Model):
    execution = models.OneToOneField(
        DashboardReportExecution,
        on_delete=models.CASCADE,
        related_name="render_token",
        verbose_name="报告执行",
    )
    attempt_no = models.PositiveSmallIntegerField(
        default=1,
        verbose_name="签发时 attempt 序号",
    )
    token_hash = models.CharField(
        max_length=64,
        unique=True,
        verbose_name="Render Token SHA-256",
    )
    expires_at = models.DateTimeField(db_index=True, verbose_name="到期时间")
    consumed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="消费时间",
    )
    revoked_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="废止时间",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="创建时间",
    )

    class Meta:
        db_table = "operation_analysis_dashboard_report_render_token"
        verbose_name = "仪表盘报告一次性 Render Token"
