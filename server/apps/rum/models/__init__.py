import uuid

from django.db import models
from django.utils import timezone


def new_id() -> str:
    return str(uuid.uuid4())


class RumIssue(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=new_id, editable=False)
    fingerprint = models.CharField(max_length=128, unique=True)
    status = models.CharField(max_length=32, default="open")
    note = models.TextField(blank=True, default="")
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_version = models.CharField(max_length=128, blank=True, default="")
    ignored_until = models.DateTimeField(null=True, blank=True)
    updated_by = models.CharField(max_length=128, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rum_issues"


class RumFunnel(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=new_id, editable=False)
    name = models.CharField(max_length=128)
    steps = models.JSONField(default=list)
    application = models.CharField(max_length=128, db_index=True, blank=True, default="")
    default_preset = models.CharField(max_length=64, blank=True, default="")
    created_by = models.CharField(max_length=128, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rum_funnels"


class RumReleaseBaseline(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=new_id, editable=False)
    application = models.CharField(max_length=128, unique=True)
    baseline_release = models.CharField(max_length=128)
    created_by = models.CharField(max_length=128, blank=True, default="")
    updated_by = models.CharField(max_length=128, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rum_release_baselines"


class RumAlertPolicy(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=new_id, editable=False)
    name = models.CharField(max_length=128)
    application = models.CharField(max_length=128, db_index=True)
    metric = models.CharField(max_length=64)
    severity = models.CharField(max_length=32, default="warning")
    comparator = models.CharField(max_length=8, default=">=")
    warn_threshold = models.FloatField(default=0)
    critical_threshold = models.FloatField(default=0)
    evaluation_window_minutes = models.PositiveIntegerField(default=15)
    for_duration_sec = models.PositiveIntegerField(default=300)
    no_data_after = models.PositiveIntegerField(default=3)
    renotify_minutes = models.PositiveIntegerField(null=True, blank=True)
    handlers = models.JSONField(default=list)
    enabled = models.BooleanField(default=True, db_index=True)
    consecutive_hits = models.PositiveIntegerField(default=0)
    consecutive_recoveries = models.PositiveIntegerField(default=0)
    consecutive_no_data = models.PositiveIntegerField(default=0)
    evaluation_cursor = models.CharField(max_length=64, blank=True, default="")
    last_succeeded_at = models.DateTimeField(null=True, blank=True)
    last_failed_at = models.DateTimeField(null=True, blank=True)
    last_evaluation_result = models.CharField(max_length=16, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rum_alert_policies"


class RumAlertPolicyOrganization(models.Model):
    policy = models.ForeignKey(RumAlertPolicy, on_delete=models.CASCADE, related_name="organization_links")
    organization = models.BigIntegerField(db_index=True)

    class Meta:
        db_table = "rum_alert_policy_organizations"
        constraints = [
            models.UniqueConstraint(fields=("policy", "organization"), name="rum_policy_org_uniq"),
        ]


class RumAlertPolicyNotificationTarget(models.Model):
    policy = models.ForeignKey(RumAlertPolicy, on_delete=models.CASCADE, related_name="notification_targets")
    channel_id = models.PositiveBigIntegerField(db_index=True)
    channel_name = models.CharField(max_length=100, blank=True, default="")
    channel_type = models.CharField(max_length=30, blank=True, default="")
    delivery_mode = models.CharField(max_length=32)
    recipient_mode = models.CharField(max_length=32)
    recipients = models.JSONField(default=list)

    class Meta:
        db_table = "rum_alert_policy_targets"
        constraints = [
            models.UniqueConstraint(fields=("policy", "channel_id"), name="rum_policy_channel_uniq"),
        ]


class RumAlert(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=new_id, editable=False)
    policy = models.ForeignKey(
        RumAlertPolicy,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="alerts",
    )
    policy_id_snapshot = models.CharField(max_length=36, db_index=True)
    policy_name = models.CharField(max_length=128)
    application = models.CharField(max_length=128, db_index=True)
    metric = models.CharField(max_length=64)
    comparator = models.CharField(max_length=8, blank=True, default="")
    warn_threshold = models.FloatField(default=0)
    critical_threshold = models.FloatField(default=0)
    severity = models.CharField(max_length=32, blank=True, default="")
    status = models.CharField(max_length=16, default="active", db_index=True)
    current_value = models.FloatField(null=True, blank=True)
    organizations = models.JSONField(default=list)
    handlers = models.JSONField(default=list)
    operator = models.CharField(max_length=150, blank=True, default="")
    renotify_count = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(db_index=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    last_event_at = models.DateTimeField(db_index=True)
    last_notified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "rum_alerts"


class RumAlertEvent(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=new_id, editable=False)
    event_key = models.CharField(max_length=320, unique=True)
    alert = models.ForeignKey(RumAlert, on_delete=models.CASCADE, related_name="events")
    action = models.CharField(max_length=16, db_index=True)
    occurred_at = models.DateTimeField(db_index=True)
    severity = models.CharField(max_length=32, blank=True, default="")
    value = models.FloatField(null=True, blank=True)
    content = models.JSONField(default=dict)
    organizations = models.JSONField(default=list)

    class Meta:
        db_table = "rum_alert_events"
        ordering = ("occurred_at", "id")


class RumAlertDelivery(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=new_id, editable=False)
    delivery_key = models.CharField(max_length=384, unique=True)
    event = models.ForeignKey(
        RumAlertEvent,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="deliveries",
    )
    alert = models.ForeignKey(RumAlert, on_delete=models.CASCADE, related_name="deliveries")
    channel_id = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)
    channel_name = models.CharField(max_length=100, blank=True, default="")
    channel_type = models.CharField(max_length=30, blank=True, default="")
    delivery_mode = models.CharField(max_length=32, blank=True, default="message")
    recipients = models.JSONField(default=list)
    title = models.CharField(max_length=512, blank=True, default="")
    body = models.TextField(blank=True, default="")
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=16, default="pending", db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    next_retry_at = models.DateTimeField(null=True, blank=True, db_index=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=128, blank=True, default="")
    last_error_message = models.CharField(max_length=512, blank=True, default="")
    delivered_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "rum_alert_deliveries"


class RumAlertDeliveryRetry(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=new_id, editable=False)
    delivery = models.ForeignKey(RumAlertDelivery, on_delete=models.CASCADE, related_name="manual_retries")
    requested_by = models.CharField(max_length=150)
    previous_attempts = models.PositiveIntegerField(default=0)
    previous_error_code = models.CharField(max_length=128, blank=True, default="")
    previous_error_message = models.CharField(max_length=512, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "rum_alert_delivery_retries"


class RumSavedView(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=new_id, editable=False)
    screen = models.CharField(max_length=64, db_index=True)
    name = models.CharField(max_length=128)
    context_json = models.TextField(blank=True, default="")
    shared = models.BooleanField(default=False, db_index=True)
    owner = models.CharField(max_length=128, db_index=True, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rum_saved_views"
        indexes = [
            models.Index(fields=["screen", "owner"], name="rum_sv_screen_owner"),
        ]


class RumSourcemap(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=new_id, editable=False)
    application = models.CharField(max_length=128, db_index=True)
    release = models.CharField(max_length=128, db_index=True)
    file_name = models.CharField(max_length=512)
    content = models.BinaryField()
    created_by = models.CharField(max_length=128, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "rum_sourcemaps"
        indexes = [
            models.Index(fields=["application", "release"], name="rum_sm_app_release"),
        ]


class RumSourcemapCredential(models.Model):
    application = models.CharField(primary_key=True, max_length=128)
    token_digest = models.CharField(max_length=128)
    created_by = models.CharField(max_length=128, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rum_sourcemap_credentials"


class RumApplication(models.Model):
    name = models.CharField(primary_key=True, max_length=128)
    tenant_id = models.CharField(max_length=128)
    org_id = models.CharField(max_length=128)
    enabled = models.BooleanField(default=True)
    revision = models.BigIntegerField(default=0)
    requests_per_minute = models.BigIntegerField(default=0)
    compressed_bytes_per_minute = models.BigIntegerField(default=0)
    decompressed_bytes_per_minute = models.BigIntegerField(default=0)
    events_per_minute = models.BigIntegerField(default=0)
    created_by = models.CharField(max_length=128, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rum_applications"


class RumApplicationOrigin(models.Model):
    application = models.CharField(max_length=128, db_index=True)
    origin = models.CharField(max_length=256)

    class Meta:
        db_table = "rum_application_origins"
        constraints = [
            models.UniqueConstraint(fields=["application", "origin"], name="rum_app_origin_uniq"),
        ]


class RumApplicationKey(models.Model):
    application = models.CharField(max_length=128, db_index=True)
    key_cipher = models.TextField()
    key_digest = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=16, default="active")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "rum_application_keys"


class RumProjectionOutbox(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=new_id, editable=False)
    kind = models.CharField(max_length=32)
    application = models.CharField(max_length=128, db_index=True)
    revision = models.BigIntegerField(default=0)
    payload_json = models.JSONField(default=dict)
    status = models.CharField(max_length=16, default="pending", db_index=True)
    attempts = models.IntegerField(default=0)
    last_error_type = models.CharField(max_length=128, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "rum_projection_outbox"
        constraints = [
            models.UniqueConstraint(
                fields=["application", "revision"],
                condition=models.Q(kind="application"),
                name="rum_outbox_app_rev_uniq",
            ),
        ]


class RumEraseJob(models.Model):
    """BK-Lite deviation from upstream: durable erase ledger instead of localStorage."""

    id = models.CharField(primary_key=True, max_length=36, default=new_id, editable=False)
    application = models.CharField(max_length=128, db_index=True)
    end_user_id = models.CharField(max_length=256, db_index=True)
    status = models.CharField(max_length=32, default="submitted", db_index=True)
    requested_by = models.CharField(max_length=128, blank=True, default="")
    result_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rum_erase_jobs"
