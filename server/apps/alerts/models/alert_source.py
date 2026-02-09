# -- coding: utf-8 --
# @File: alert_source.py
# @Time: 2026/2/5 16:22
# @Author: windyzhao
from django.db import models
from django.db.models import JSONField

from apps.alerts.constants.constants import AlertsSourceTypes, AlertAccessType
from apps.alerts.utils.util import gen_app_secret
from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


# 只查询未被软删除的对象
class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_delete=False)


class AlertSource(MaintainerInfo, TimeInfo):
    """告警源配置"""

    name = models.CharField(max_length=100, help_text="告警源名称")
    source_id = models.CharField(
        max_length=100, unique=True, db_index=True, help_text="告警源ID"
    )
    source_type = models.CharField(
        max_length=20, choices=AlertsSourceTypes.CHOICES, help_text="告警源类型"
    )
    config = JSONField(default=dict, help_text="告警源配置")
    secret = models.CharField("密钥", max_length=100, default=gen_app_secret)
    logo = models.TextField(null=True, blank=True, help_text="告警源logo")  # base64
    access_type = models.CharField(
        max_length=64,
        choices=AlertAccessType.CHOICES,
        default=AlertAccessType.BUILT_IN,
        help_text="告警源接入类型",
    )
    is_active = models.BooleanField(default=True, db_index=True, help_text="是否启用")
    is_effective = models.BooleanField(
        default=True, db_index=False, help_text="是否生效"
    )
    description = models.TextField(null=True, blank=True, help_text="告警源描述")
    last_active_time = models.DateTimeField(
        null=True, blank=True, help_text="最近活跃时间"
    )
    is_delete = models.BooleanField(default=False, db_index=True, help_text="是否删除")

    class Meta:
        indexes = [
            models.Index(fields=["name", "source_type"]),
        ]

    all_objects = models.Manager()  # 所有对象，包括被软删除的对象
    objects = SoftDeleteManager()  # 只查询未被软删除的对象

    def __str__(self):
        return f"{self.name} ({self.source_type})"
