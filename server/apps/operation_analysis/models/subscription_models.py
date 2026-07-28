from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models.time_info import TimeInfo
from apps.operation_analysis.models.models import Dashboard


class DashboardReportSubscription(TimeInfo):
    class Status(models.TextChoices):
        ACTIVE = "active", "启用"
        PAUSED = "paused", "暂停"
        TERMINATED = "terminated", "已终止"

    dashboard = models.ForeignKey(
        Dashboard,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="report_subscriptions",
        verbose_name="仪表盘",
    )
    creator = models.CharField(max_length=32, db_index=True, verbose_name="创建者")
    name = models.CharField(max_length=128, verbose_name="订阅名称")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
        verbose_name="状态",
    )
    recipient_email = models.EmailField(verbose_name="接收邮箱")
    config = models.JSONField(default=dict, blank=True, verbose_name="扩展配置")

    class Meta:
        db_table = "operation_analysis_dashboard_report_subscription"
        verbose_name = "仪表盘报告订阅"
        ordering = ["-id"]

    def clean(self):
        super().clean()
        if self.status == self.Status.ACTIVE and self.dashboard_id is None:
            raise ValidationError(
                {"dashboard": "启用状态的报告订阅必须关联仪表盘"}
            )

    def __str__(self):
        return self.name
