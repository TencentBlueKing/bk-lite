# -- coding: utf-8 --
# @File: sys_setting.py
# @Time: 2026/2/5 16:18
# @Author: windyzhao
from django.db import models
from django.db.models import JSONField

from apps.core.models.time_info import TimeInfo


class SystemSetting(TimeInfo):
    """系统设置模型"""

    key = models.CharField(max_length=100, unique=True, help_text="设置键")
    value = JSONField(help_text="设置值", default=dict)
    description = models.TextField(null=True, blank=True, help_text="设置描述")
    is_activate = models.BooleanField(
        default=False, db_index=True, help_text="是否启用"
    )
    is_build = models.BooleanField(
        default=True, db_index=True, help_text="是否为内置设置"
    )

    class Meta:
        db_table = "alerts_system_setting"
        verbose_name = "系统设置"
        verbose_name_plural = "系统设置"

    def __str__(self):
        return self.key

