"""全局扫描设置模型"""

from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class ScanSetting(TimeInfo, MaintainerInfo):
    """全局扫描/评估周期配置

    单例模式：全系统只有一条记录，控制所有目标的周期性合规评估。
    """

    FREQUENCY_CHOICES = (
        ("hourly", "每小时"),
        ("daily", "每天"),
        ("weekly", "每周"),
    )

    frequency = models.CharField(
        max_length=16,
        choices=FREQUENCY_CHOICES,
        default="daily",
        verbose_name="评估周期",
    )
    # hourly 专用：每 N 小时执行一次
    hour_interval = models.PositiveIntegerField(default=1, verbose_name="小时间隔")
    # weekly 专用：周几执行（1=周一，7=周日）
    weekday = models.PositiveSmallIntegerField(default=1, verbose_name="周几")
    # daily/weekly 专用：执行时间 HH:MM
    time = models.CharField(max_length=5, default="02:00", verbose_name="执行时间")
    is_enabled = models.BooleanField(default=True, verbose_name="是否启用")

    class Meta:
        db_table = "patch_scan_setting"
        verbose_name = "扫描设置"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"扫描设置({self.get_frequency_display()})"

    @classmethod
    def get_singleton(cls):
        """获取或创建唯一配置记录"""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
