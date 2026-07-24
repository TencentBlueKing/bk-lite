import uuid

from django.db import models
from django.utils import timezone


class DashboardShareLink(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "有效"
        SHARER_PERMISSION_LOST = "sharer_permission_lost", "分享者失权"
        DASHBOARD_INVALID = "dashboard_invalid", "画布失效"

    dashboard = models.ForeignKey(
        "operation_analysis.Dashboard",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="share_links",
    )
    dashboard_instance_id = models.PositiveBigIntegerField(db_index=True)
    tenant_domain = models.CharField(max_length=100, db_index=True)
    space_id = models.PositiveBigIntegerField(db_index=True)
    sharer_username = models.CharField(max_length=100)
    sharer_domain = models.CharField(max_length=100)
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.ACTIVE)
    invalidated_at = models.DateTimeField(null=True, blank=True)
    invalidated_by = models.CharField(max_length=201, blank=True, default="")
    invalidation_reason = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "operation_analysis_dashboard_share_link"
        constraints = [
            models.UniqueConstraint(
                fields=["dashboard_instance_id", "sharer_username", "sharer_domain"],
                condition=models.Q(status="active"),
                name="uniq_active_dashboard_share_by_sharer",
            )
        ]
        indexes = [
            models.Index(fields=["status"], name="op_share_status_idx"),
        ]

    def is_usable(self):
        return self.status == self.Status.ACTIVE

    def mark_invalid(self, reason, actor=""):
        if self.status != self.Status.ACTIVE:
            return
        self.status = reason
        self.invalidated_at = timezone.now()
        self.invalidated_by = actor
        self.invalidation_reason = reason
        self.save(
            update_fields=[
                "status",
                "invalidated_at",
                "invalidated_by",
                "invalidation_reason",
                "updated_at",
            ]
        )


class DashboardShareSession(models.Model):
    session_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    share_link = models.ForeignKey(DashboardShareLink, on_delete=models.CASCADE, related_name="sessions")
    visitor_username = models.CharField(max_length=100)
    visitor_domain = models.CharField(max_length=100)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    refreshed_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "operation_analysis_dashboard_share_session"
        constraints = [
            models.UniqueConstraint(
                fields=["share_link", "visitor_username", "visitor_domain"],
                name="uniq_share_session_by_visitor",
            )
        ]
