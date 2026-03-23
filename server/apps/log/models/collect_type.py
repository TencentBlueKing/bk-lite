from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class CollectType(TimeInfo, MaintainerInfo):
    name = models.CharField(max_length=100, verbose_name="采集方式")
    collector = models.CharField(max_length=100, verbose_name="采集器")
    icon = models.CharField(max_length=100, verbose_name="图标")
    description = models.TextField(blank=True, verbose_name="描述")
    default_query = models.TextField(blank=True, verbose_name="默认查询语句")
    attrs = models.JSONField(default=list, verbose_name="属性列表")
    config_section = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="配置段",
    )
    display_category = models.CharField(
        max_length=50,
        default="",
        verbose_name="展示分类",
    )

    class Meta:
        verbose_name = "采集方式"
        verbose_name_plural = "采集方式"
        unique_together = ("name", "collector")
