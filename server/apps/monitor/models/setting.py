from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class Setting(TimeInfo, MaintainerInfo):
    name = models.CharField(max_length=100, verbose_name='设置名称')
    value = models.JSONField(default=dict, verbose_name='设置值')

    class Meta:
        verbose_name = '设置'
        verbose_name_plural = '设置'
