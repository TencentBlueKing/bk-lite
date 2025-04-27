from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class PackageVersion(TimeInfo, MaintainerInfo):
    type = models.CharField(db_index=True, max_length=100, verbose_name="包类型(控制器/采集器)")
    os = models.CharField(db_index=True, max_length=20, verbose_name="操作系统")
    object = models.CharField(db_index=True, max_length=100, verbose_name="包对象")
    version = models.CharField(max_length=100, verbose_name="包版本号")
    name = models.CharField(max_length=100, verbose_name="包名称")
    description = models.TextField(blank=True, verbose_name="包版本描述")

    class Meta:
        verbose_name = "包版本信息"
        verbose_name_plural = "包版本信息"
        unique_together = ('os', 'object', 'version')