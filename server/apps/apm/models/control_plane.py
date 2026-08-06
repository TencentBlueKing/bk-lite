import uuid
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, models
from django.db.models import Q

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.core.utils.database_constraints import ConstraintValidatedQuerySet


class AuditedModel(TimeInfo, MaintainerInfo):
    class Meta:
        abstract = True


class ApmConstraintQuerySet(ConstraintValidatedQuerySet):
    protected_fields = frozenset(
        {"normalized_name", "normalized_instance_id", "objective", "sli_type", "latency_threshold_ms"}
    )


class ApmApplication(AuditedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application_id = models.CharField(max_length=128, unique=True)
    name = models.CharField(max_length=128)
    description = models.CharField(max_length=512, blank=True, default="")
    is_builtin = models.BooleanField(default=False, db_index=True)

    class Meta:
        verbose_name = "APM 应用"
        verbose_name_plural = "APM 应用"
        ordering = ("application_id", "id")


class ApmApplicationOrganization(AuditedModel):
    application = models.ForeignKey(
        ApmApplication,
        on_delete=models.CASCADE,
        related_name="organization_links",
    )
    organization = models.BigIntegerField(db_index=True)

    class Meta:
        verbose_name = "APM 应用组织"
        verbose_name_plural = "APM 应用组织"
        constraints = [
            models.UniqueConstraint(
                fields=("application", "organization"),
                name="apm_application_org_unique",
            )
        ]


class ApmService(AuditedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        ApmApplication,
        on_delete=models.PROTECT,
        related_name="services",
        null=True,
        blank=True,
    )
    namespace = models.CharField(max_length=256, blank=True, default="")
    normalized_namespace = models.CharField(max_length=256, blank=True, default="")
    name = models.CharField(max_length=256)
    normalized_name = models.CharField(max_length=256)
    first_seen_at = models.DateTimeField(db_index=True)
    last_seen_at = models.DateTimeField(db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)
    archive_reason = models.CharField(max_length=256, blank=True, default="")

    objects = ApmConstraintQuerySet.as_manager()

    class Meta:
        verbose_name = "APM 服务"
        verbose_name_plural = "APM 服务"
        ordering = ("normalized_namespace", "normalized_name", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("normalized_namespace", "normalized_name"),
                name="apm_service_identity_unique",
            ),
            models.CheckConstraint(
                check=~Q(normalized_name=""),
                name="apm_service_name_not_empty",
            ),
        ]

    def _validate_database_constraints(self):
        if self.normalized_name == "":
            raise IntegrityError("apm_service_name_not_empty")

    def save(self, *args, **kwargs):
        self._validate_database_constraints()
        return super().save(*args, **kwargs)


class ApmServiceOrganization(AuditedModel):
    service = models.ForeignKey(
        ApmService,
        on_delete=models.CASCADE,
        related_name="organization_links",
    )
    organization = models.BigIntegerField(db_index=True)

    class Meta:
        verbose_name = "APM 服务组织"
        verbose_name_plural = "APM 服务组织"
        constraints = [
            models.UniqueConstraint(
                fields=("service", "organization"),
                name="apm_service_org_unique",
            )
        ]


class ApmServiceInstance(AuditedModel):
    class PermissionMode(models.TextChoices):
        INHERITED = "inherited", "继承应用"
        CUSTOM = "custom", "自定义"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    service = models.ForeignKey(
        ApmService,
        on_delete=models.CASCADE,
        related_name="instances",
    )
    instance_id = models.CharField(max_length=512)
    normalized_instance_id = models.CharField(max_length=512)
    environment = models.CharField(max_length=256, blank=True, default="")
    version = models.CharField(max_length=256, blank=True, default="")
    permission_mode = models.CharField(
        max_length=16,
        choices=PermissionMode.choices,
        default=PermissionMode.INHERITED,
    )
    first_seen_at = models.DateTimeField(db_index=True)
    last_seen_at = models.DateTimeField(db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)
    archive_reason = models.CharField(max_length=256, blank=True, default="")

    objects = ApmConstraintQuerySet.as_manager()

    class Meta:
        verbose_name = "APM 服务实例"
        verbose_name_plural = "APM 服务实例"
        ordering = ("service_id", "normalized_instance_id", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("service", "normalized_instance_id"),
                name="apm_service_instance_identity_unique",
            ),
            models.CheckConstraint(
                check=~Q(normalized_instance_id=""),
                name="apm_instance_id_not_empty",
            ),
        ]

    def _validate_database_constraints(self):
        if self.normalized_instance_id == "":
            raise IntegrityError("apm_instance_id_not_empty")

    def save(self, *args, **kwargs):
        self._validate_database_constraints()
        return super().save(*args, **kwargs)


class ApmServiceInstanceOrganization(AuditedModel):
    instance = models.ForeignKey(
        ApmServiceInstance,
        on_delete=models.CASCADE,
        related_name="organization_links",
    )
    organization = models.BigIntegerField(db_index=True)

    class Meta:
        verbose_name = "APM 服务实例组织"
        verbose_name_plural = "APM 服务实例组织"
        constraints = [
            models.UniqueConstraint(
                fields=("instance", "organization"),
                name="apm_instance_org_unique",
            )
        ]


class ApmSlo(AuditedModel):
    class SliType(models.TextChoices):
        AVAILABILITY = "availability", "可用性"
        LATENCY_P95 = "latency_p95", "P95 时延"
        LATENCY_P99 = "latency_p99", "P99 时延"

    class EvaluationWindow(models.TextChoices):
        ROLLING_7D = "rolling7d", "滚动 7 天"
        ROLLING_30D = "rolling30d", "滚动 30 天"
        CALENDAR_MONTH = "calendarMonth", "自然月"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=128)
    service = models.ForeignKey(ApmService, on_delete=models.CASCADE, related_name="slos")
    environment = models.CharField(max_length=256)
    endpoint = models.CharField(max_length=512, blank=True, default="")
    sli_type = models.CharField(max_length=32, choices=SliType.choices)
    objective = models.DecimalField(max_digits=6, decimal_places=3)
    latency_threshold_ms = models.PositiveIntegerField(null=True, blank=True)
    evaluation_window = models.CharField(max_length=32, choices=EvaluationWindow.choices)
    is_enabled = models.BooleanField(default=True, db_index=True)

    objects = ApmConstraintQuerySet.as_manager()

    class Meta:
        verbose_name = "APM SLO"
        verbose_name_plural = "APM SLO"
        ordering = ("name", "id")
        constraints = [
            models.CheckConstraint(
                check=Q(objective__gt=0) & Q(objective__lte=100),
                name="apm_slo_objective_range",
            ),
            models.CheckConstraint(
                check=(
                    Q(sli_type="availability", latency_threshold_ms__isnull=True)
                    | Q(sli_type__in=("latency_p95", "latency_p99"), latency_threshold_ms__gt=0)
                ),
                name="apm_slo_latency_threshold_shape",
            ),
        ]

    def _validate_database_constraints(self):
        try:
            objective = Decimal(str(self.objective))
            valid_objective = objective.is_finite() and 0 < objective <= 100
        except (InvalidOperation, TypeError, ValueError):
            raise IntegrityError("apm_slo_objective_range") from None
        if not valid_objective:
            raise IntegrityError("apm_slo_objective_range")
        valid_latency_shape = (self.sli_type == self.SliType.AVAILABILITY and self.latency_threshold_ms is None) or (
            self.sli_type in {self.SliType.LATENCY_P95, self.SliType.LATENCY_P99}
            and self.latency_threshold_ms is not None
            and self.latency_threshold_ms > 0
        )
        if not valid_latency_shape:
            raise IntegrityError("apm_slo_latency_threshold_shape")

    def save(self, *args, **kwargs):
        self._validate_database_constraints()
        return super().save(*args, **kwargs)


class ApmPolicy(AuditedModel):
    class MetricType(models.TextChoices):
        ERROR_RATE = "error_rate", "错误率"
        P95 = "p95", "P95"
        P99 = "p99", "P99"
        THROUGHPUT = "throughput", "吞吐"
        NO_TRAFFIC = "no_traffic", "无流量"

    class Comparator(models.TextChoices):
        GREATER_THAN = "gt", ">"
        GREATER_THAN_OR_EQUAL = "gte", ">="
        LESS_THAN = "lt", "<"
        LESS_THAN_OR_EQUAL = "lte", "<="

    class Severity(models.TextChoices):
        CRITICAL = "critical", "严重"
        ERROR = "error", "错误"
        WARNING = "warning", "警告"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=256)
    service = models.ForeignKey(ApmService, on_delete=models.CASCADE, related_name="policies")
    environment = models.CharField(max_length=256)
    metric_type = models.CharField(max_length=32, choices=MetricType.choices)
    comparator = models.CharField(max_length=8, choices=Comparator.choices)
    threshold = models.DecimalField(max_digits=20, decimal_places=6)
    duration_window = models.PositiveIntegerField()
    recovery_window = models.PositiveIntegerField()
    severity = models.CharField(max_length=16, choices=Severity.choices)
    notice = models.BooleanField(default=False)
    notice_type_ids = models.JSONField(default=list)
    notice_users = models.JSONField(default=list)
    is_enabled = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name = "APM 策略"
        verbose_name_plural = "APM 策略"
        ordering = ("name", "id")


class ApmPolicyNotificationTarget(AuditedModel):
    class DeliveryMode(models.TextChoices):
        MESSAGE = "message", "普通通知"
        ALERT_EVENT_COPY = "alert_event_copy", "告警中心事件副本"

    class RecipientMode(models.TextChoices):
        NONE = "none", "无需接收人"
        SYSTEM_USER = "system_user", "系统用户"
        FREE_TEXT = "free_text", "自由输入"

    policy = models.ForeignKey(
        ApmPolicy,
        on_delete=models.CASCADE,
        related_name="notification_targets",
    )
    channel_id = models.PositiveBigIntegerField(db_index=True)
    channel_name = models.CharField(max_length=100, blank=True, default="")
    channel_type = models.CharField(max_length=30, blank=True, default="")
    delivery_mode = models.CharField(max_length=32, choices=DeliveryMode.choices)
    recipient_mode = models.CharField(max_length=32, choices=RecipientMode.choices)
    recipients = models.JSONField(default=list)

    class Meta:
        verbose_name = "APM 策略通知目标"
        verbose_name_plural = "APM 策略通知目标"
        ordering = ("channel_id", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("policy", "channel_id"),
                name="apm_policy_notification_target_unique",
            )
        ]


class ApmPolicyState(AuditedModel):
    class Status(models.TextChoices):
        NORMAL = "normal", "正常"
        FIRING = "firing", "告警"

    policy = models.OneToOneField(ApmPolicy, on_delete=models.CASCADE, related_name="state")
    evaluation_cursor = models.CharField(max_length=512, blank=True, default="")
    consecutive_hits = models.PositiveIntegerField(default=0)
    consecutive_recoveries = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NORMAL)
    last_succeeded_at = models.DateTimeField(null=True, blank=True)
    last_failed_at = models.DateTimeField(null=True, blank=True)
    external_alert_id = models.CharField(max_length=256, blank=True, default="")

    class Meta:
        verbose_name = "APM 策略状态"
        verbose_name_plural = "APM 策略状态"


class ApmAlert(AuditedModel):
    class Status(models.TextChoices):
        FIRING = "firing", "告警中"
        RECOVERED = "recovered", "已恢复"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    external_id = models.CharField(max_length=256, unique=True)
    policy = models.ForeignKey(
        ApmPolicy,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="alerts",
    )
    service = models.ForeignKey(
        ApmService,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="alerts",
    )
    policy_id_snapshot = models.CharField(max_length=36)
    policy_name = models.CharField(max_length=256)
    service_namespace = models.CharField(max_length=256, blank=True, default="")
    service_name = models.CharField(max_length=256)
    environment = models.CharField(max_length=256, blank=True, default="")
    metric_type = models.CharField(max_length=32, choices=ApmPolicy.MetricType.choices)
    severity = models.CharField(max_length=16, choices=ApmPolicy.Severity.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.FIRING, db_index=True)
    current_value = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    organizations = models.JSONField(default=list)
    started_at = models.DateTimeField(db_index=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    last_event_at = models.DateTimeField(db_index=True)

    class Meta:
        verbose_name = "APM 告警"
        verbose_name_plural = "APM 告警"
        ordering = ("-last_event_at", "-id")


class ApmEvent(AuditedModel):
    class Action(models.TextChoices):
        CREATED = "created", "触发"
        RECOVERY = "recovery", "恢复"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_id = models.CharField(max_length=320, unique=True)
    alert = models.ForeignKey(ApmAlert, on_delete=models.CASCADE, related_name="events")
    action = models.CharField(max_length=16, choices=Action.choices, db_index=True)
    title = models.CharField(max_length=512)
    description = models.TextField(blank=True, default="")
    severity = models.CharField(max_length=16, choices=ApmPolicy.Severity.choices, db_index=True)
    service = models.CharField(max_length=256)
    item = models.CharField(max_length=32, choices=ApmPolicy.MetricType.choices)
    value = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True)
    resource_id = models.CharField(max_length=36)
    resource_name = models.CharField(max_length=512)
    policy_id = models.CharField(max_length=36, db_index=True)
    environment = models.CharField(max_length=256, blank=True, default="")
    organizations = models.JSONField(default=list)
    occurred_at = models.DateTimeField(db_index=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "APM 告警事件"
        verbose_name_plural = "APM 告警事件"
        ordering = ("-occurred_at", "-id")


class ApmAlertOutbox(AuditedModel):
    class DeliveryStatus(models.TextChoices):
        PENDING = "pending", "待投递"
        DELIVERED = "delivered", "已投递"
        FAILED = "failed", "终止失败"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_key = models.CharField(max_length=384, unique=True)
    event = models.ForeignKey(
        ApmEvent,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="outbox_entries",
    )
    channel_id = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)
    receivers = models.JSONField(default=list)
    recipients = models.JSONField(default=list)
    channel_name = models.CharField(max_length=100, blank=True, default="")
    channel_type = models.CharField(max_length=30, blank=True, default="")
    delivery_mode = models.CharField(max_length=32, blank=True, default="message")
    title = models.CharField(max_length=512, blank=True, default="")
    body = models.TextField(blank=True, default="")
    payload = models.JSONField(default=dict)
    delivery_status = models.CharField(
        max_length=16,
        choices=DeliveryStatus.choices,
        default=DeliveryStatus.PENDING,
        db_index=True,
    )
    attempts = models.PositiveIntegerField(default=0)
    next_retry_at = models.DateTimeField(null=True, blank=True, db_index=True)
    claimed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_error_code = models.CharField(max_length=128, blank=True, default="")
    last_error_message = models.CharField(max_length=512, blank=True, default="")
    delivered_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "APM 告警投递箱"
        verbose_name_plural = "APM 告警投递箱"
        ordering = ("created_at", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("event", "channel_id"),
                condition=Q(event__isnull=False, channel_id__isnull=False),
                name="apm_outbox_event_channel_unique",
            ),
            models.UniqueConstraint(
                fields=("event", "channel_id"),
                name="apm_outbox_event_channel_portable_unique",
            ),
        ]


class ApmNotificationDeliveryRetry(AuditedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    delivery = models.ForeignKey(
        ApmAlertOutbox,
        on_delete=models.CASCADE,
        related_name="manual_retries",
    )
    requested_by = models.CharField(max_length=150)
    previous_attempts = models.PositiveIntegerField(default=0)
    previous_error_code = models.CharField(max_length=128, blank=True, default="")
    previous_error_message = models.CharField(max_length=512, blank=True, default="")

    class Meta:
        verbose_name = "APM 通知人工重投审计"
        verbose_name_plural = "APM 通知人工重投审计"
        ordering = ("-created_at", "-id")
