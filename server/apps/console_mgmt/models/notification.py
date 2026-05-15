from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Notification(models.Model):
    """通知消息模型"""

    notification_time = models.DateTimeField(auto_now_add=True, verbose_name=_("通知时间"), db_index=True)
    app_module = models.CharField(max_length=100, verbose_name=_("模块"), db_index=True)
    content = models.TextField(verbose_name=_("通知内容"))
    is_read = models.BooleanField(default=False, verbose_name=_("是否已读（已废弃，保留兼容）"), db_index=True)
    source = models.CharField(max_length=100, default="unknown", verbose_name=_("来源"))

    class Meta:
        verbose_name = _("通知消息")
        verbose_name_plural = _("通知消息")
        db_table = "console_mgmt_notification"
        ordering = ["-notification_time"]
        indexes = [
            models.Index(fields=["is_read", "-notification_time"]),
            models.Index(fields=["app_module", "-notification_time"]),
        ]

    def __str__(self):
        return f"{self.app_module} - {self.notification_time}"


class NotificationRead(models.Model):
    """用户-通知已读状态（每用户独立）"""

    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name="read_states")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_reads")
    is_read = models.BooleanField(default=False, verbose_name=_("是否已读"))
    read_at = models.DateTimeField(null=True, blank=True, verbose_name=_("已读时间"))
    is_deleted = models.BooleanField(default=False, verbose_name=_("是否已删除"))

    class Meta:
        verbose_name = _("通知已读状态")
        verbose_name_plural = _("通知已读状态")
        db_table = "console_mgmt_notification_read"
        unique_together = ("notification", "user")
        indexes = [
            models.Index(fields=["user", "is_read"]),
            models.Index(fields=["user", "is_deleted"]),
        ]

    def __str__(self):
        return f"User {self.user_id} - Notification {self.notification_id}"
