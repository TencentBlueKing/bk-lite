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
    severity = models.CharField(max_length=32, default="critical")
    comparator = models.CharField(max_length=8, default=">")
    warn_threshold = models.FloatField(default=0)
    critical_threshold = models.FloatField(default=0)
    for_duration_sec = models.IntegerField(default=0)
    no_data = models.BooleanField(default=False)
    renotify_minutes = models.IntegerField(null=True, blank=True)
    enabled = models.BooleanField(default=True, db_index=True)
    signal = models.CharField(max_length=64, blank=True, default="")
    notify_channels = models.JSONField(default=list)
    pending_since = models.DateTimeField(null=True, blank=True)
    recovering_since = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rum_alert_policies"


class RumAlertEvent(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=new_id, editable=False)
    policy_id = models.CharField(max_length=36, db_index=True)
    status = models.CharField(max_length=32, db_index=True)
    severity = models.CharField(max_length=32, blank=True, default="")
    metric_value = models.FloatField(default=0)
    message = models.TextField(blank=True, default="")
    fired_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    last_notified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "rum_alert_events"


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
