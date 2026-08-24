import uuid

from django.db import models
from django.utils import timezone

from apps.core.utils.conditional_unique import ConditionalUniqueGuardQuerySet


class DashboardShareLinkQuerySet(ConditionalUniqueGuardQuerySet):
    guard_rules = {"status": ("active_guard", lambda status: True if status == "active" else None)}


class DashboardShareLink(models.Model):
    class ResourceType(models.TextChoices):
        DASHBOARD = "dashboard", "仪表盘"
        TOPOLOGY = "topology", "拓扑图"
        ARCHITECTURE = "architecture", "架构图"
        SCREEN = "screen", "大屏"
        REPORT = "report", "报表"
        NETWORK_TOPOLOGY = "networkTopology", "网络拓扑"

    class Status(models.TextChoices):
        ACTIVE = "active", "有效"
        SHARER_PERMISSION_LOST = "sharer_permission_lost", "分享者失权"
        DASHBOARD_INVALID = "dashboard_invalid", "画布失效"

    resource_type = models.CharField(
        max_length=32,
        choices=ResourceType.choices,
        default=ResourceType.DASHBOARD,
        db_index=True,
    )
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
    active_guard = models.BooleanField(null=True, default=None, editable=False)

    objects = DashboardShareLinkQuerySet.as_manager()

    class Meta:
        db_table = "operation_analysis_dashboard_share_link"
        constraints = [
            models.UniqueConstraint(
                fields=["resource_type", "dashboard_instance_id", "sharer_username", "sharer_domain"],
                condition=models.Q(status="active"),
                name="uniq_active_canvas_share_by_sharer",
            ),
            models.UniqueConstraint(
                fields=[
                    "resource_type",
                    "dashboard_instance_id",
                    "sharer_username",
                    "sharer_domain",
                    "active_guard",
                ],
                name="uniq_active_canvas_share_guard",
            ),
        ]
        indexes = [
            models.Index(fields=["status"], name="op_share_status_idx"),
        ]

    def is_usable(self):
        return self.status == self.Status.ACTIVE

    def save(self, *args, **kwargs):
        self.active_guard = True if self.status == self.Status.ACTIVE else None
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "status" in update_fields:
            kwargs["update_fields"] = set(update_fields) | {"active_guard"}
        return super().save(*args, **kwargs)

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
