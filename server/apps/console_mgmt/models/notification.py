from django.db import models
from django.utils.translation import gettext_lazy as _


class Notification(models.Model):
    """通知消息模型"""

    notification_time = models.DateTimeField(auto_now_add=True, verbose_name=_("通知时间"), db_index=True)
    app_module = models.CharField(max_length=100, verbose_name=_("模块"), db_index=True)
    content = models.TextField(verbose_name=_("通知内容"))
    is_read = models.BooleanField(default=False, verbose_name=_("是否已读"), db_index=True)

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

    def mark_as_read(self):
        """标记为已读"""
        if not self.is_read:
            self.is_read = True
            self.save(update_fields=["is_read"])

    def mark_as_unread(self):
        """标记为未读"""
        if self.is_read:
            self.is_read = False
            self.save(update_fields=["is_read"])
