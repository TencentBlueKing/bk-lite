import hashlib

from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class NotificationTemplate(MaintainerInfo, TimeInfo):
    SCOPE_SINGLE_ALERT = "single_alert"
    SCOPE_UNASSIGNED_SUMMARY = "unassigned_summary"
    SCOPE_ALERT_OPERATION = "alert_operation"
    SCOPE_CHOICES = (
        (SCOPE_SINGLE_ALERT, "单告警"),
        (SCOPE_UNASSIGNED_SUMMARY, "未分派汇总"),
        (SCOPE_ALERT_OPERATION, "告警操作"),
    )

    name = models.CharField(max_length=100, help_text="模板名称")
    description = models.CharField(max_length=500, blank=True, default="", help_text="模板说明")
    team = models.JSONField(default=list, help_text="关联组织")
    scope_key = models.CharField(max_length=70, editable=False, db_index=True, help_text="组织范围唯一键")
    scope = models.CharField(max_length=32, choices=SCOPE_CHOICES, default=SCOPE_SINGLE_ALERT, db_index=True)
    is_global = models.BooleanField(default=False, db_index=True, help_text="是否为全局模板")
    builtin_key = models.CharField(max_length=64, blank=True, default="", db_index=True, help_text="内置模板稳定标识")
    channel_id = models.PositiveBigIntegerField(null=True, blank=True, help_text="内置告警操作模板绑定的唯一通知渠道")
    revision = models.PositiveIntegerField(default=1, help_text="乐观锁版本")

    class Meta:
        db_table = "alerts_notification_template"
        ordering = ["-updated_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["scope_key", "scope", "name"],
                name="alerts_notification_template_scope_name_uniq",
            ),
            models.UniqueConstraint(
                fields=["builtin_key"],
                condition=~models.Q(builtin_key=""),
                name="alerts_notification_template_builtin_key_uniq",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.is_global:
            self.team = []
            self.scope_key = "global"
        else:
            self.team = sorted({int(team_id) for team_id in (self.team or [])})
            team_key = ",".join(str(team_id) for team_id in self.team)
            self.scope_key = "team:" + hashlib.sha256(team_key.encode("utf-8")).hexdigest()
        super().save(*args, **kwargs)

    @property
    def is_builtin(self):
        return bool(self.builtin_key)

    @property
    def is_alert_operation(self):
        return self.scope == self.SCOPE_ALERT_OPERATION


class NotificationTemplateContent(models.Model):
    template = models.ForeignKey(NotificationTemplate, related_name="contents", on_delete=models.CASCADE)
    channel_type = models.CharField(max_length=30, help_text="通知渠道类型")
    subject_template = models.CharField(max_length=500, blank=True, default="", help_text="标题模板")
    body_template = models.TextField(help_text="正文模板")

    class Meta:
        db_table = "alerts_notification_template_content"
        ordering = ["id"]
        constraints = [models.UniqueConstraint(fields=["template", "channel_type"], name="alerts_notification_template_channel_uniq")]


class NotificationTemplateReference(models.Model):
    template = models.ForeignKey(NotificationTemplate, related_name="references", on_delete=models.PROTECT)
    source_type = models.CharField(max_length=32, help_text="引用来源")
    source_id = models.CharField(max_length=100, help_text="来源对象 ID")
    scene = models.CharField(max_length=32, default="default", help_text="通知场景")
    channel_id = models.IntegerField(null=True, blank=True, help_text="渠道 ID")
    locator = models.CharField(max_length=200, default="", blank=True, help_text="来源内定位")
    is_snapshot = models.BooleanField(default=False, help_text="是否为运行快照引用")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "alerts_notification_template_reference"
        indexes = [models.Index(fields=["source_type", "source_id"], name="alerts_tpl_ref_source_idx")]
        constraints = [
            models.UniqueConstraint(
                fields=["template", "source_type", "source_id", "scene", "channel_id", "locator"],
                name="alerts_notification_template_reference_uniq",
            )
        ]
