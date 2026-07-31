import uuid

from django.db import models
from django.db.models import Q

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class AuditedModel(TimeInfo, MaintainerInfo):
    class Meta:
        abstract = True


class ApmIngestSource(AuditedModel):
    class IngestType(models.TextChoices):
        OTLP_HTTP = "otlp_http", "OTLP/HTTP"
        OTLP_GRPC = "otlp_grpc", "OTLP/gRPC"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=128)
    ingest_type = models.CharField(max_length=32, choices=IngestType.choices)
    cloud_region_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    environment_hint = models.CharField(max_length=128, blank=True, default="")
    credential_digest = models.CharField(max_length=256)
    credential_prefix = models.CharField(max_length=24, db_index=True)
    is_enabled = models.BooleanField(default=True, db_index=True)
    first_received_at = models.DateTimeField(null=True, blank=True)
    last_received_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_missing_instance_identity_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        verbose_name = "APM 接入源"
        verbose_name_plural = "APM 接入源"
        ordering = ("name", "id")


class ApmIngestSourceOrganization(AuditedModel):
    ingest_source = models.ForeignKey(
        ApmIngestSource,
        on_delete=models.CASCADE,
        related_name="organization_links",
    )
    organization = models.BigIntegerField(db_index=True)

    class Meta:
        verbose_name = "APM 接入源组织"
        verbose_name_plural = "APM 接入源组织"
        constraints = [
            models.UniqueConstraint(
                fields=("ingest_source", "organization"),
                name="apm_ingest_source_org_unique",
            )
        ]


class ApmService(AuditedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    namespace = models.CharField(max_length=256, blank=True, default="")
    normalized_namespace = models.CharField(max_length=256, blank=True, default="")
    name = models.CharField(max_length=256)
    normalized_name = models.CharField(max_length=256)
    first_seen_at = models.DateTimeField(db_index=True)
    last_seen_at = models.DateTimeField(db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)
    archive_reason = models.CharField(max_length=256, blank=True, default="")

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
        INHERITED = "inherited", "继承接入源"
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
    ingest_source = models.ForeignKey(
        ApmIngestSource,
        on_delete=models.PROTECT,
        related_name="instances",
    )
    permission_mode = models.CharField(
        max_length=16,
        choices=PermissionMode.choices,
        default=PermissionMode.INHERITED,
    )
    first_seen_at = models.DateTimeField(db_index=True)
    last_seen_at = models.DateTimeField(db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)
    archive_reason = models.CharField(max_length=256, blank=True, default="")

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
    payload = models.JSONField(default=dict)
    delivery_status = models.CharField(
        max_length=16,
        choices=DeliveryStatus.choices,
        default=DeliveryStatus.PENDING,
        db_index=True,
    )
    attempts = models.PositiveIntegerField(default=0)
    next_retry_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        verbose_name = "APM 告警投递箱"
        verbose_name_plural = "APM 告警投递箱"
        ordering = ("created_at", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("event", "channel_id"),
                condition=Q(event__isnull=False, channel_id__isnull=False),
                name="apm_outbox_event_channel_unique",
            )
        ]
