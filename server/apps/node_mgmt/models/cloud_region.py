from django.db import models
from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class CloudRegion(TimeInfo, MaintainerInfo):
    name = models.CharField(unique=True, max_length=100, verbose_name="云区域名称")
    introduction = models.TextField(blank=True, verbose_name="云区域介绍")

    class Meta:
        verbose_name = "云区域"
        verbose_name_plural = "云区域"


class SidecarEnv(models.Model):
    key = models.CharField(max_length=100)
    value = models.CharField(max_length=200)
    type = models.CharField(max_length=20, default="")
    description = models.TextField(blank=True, verbose_name="描述")
    cloud_region = models.ForeignKey(CloudRegion, default=1, on_delete=models.CASCADE, verbose_name="云区域")
    is_pre = models.BooleanField(default=False, verbose_name="是否预置变量")

    class Meta:
        verbose_name = "Sidecar环境变量"
        verbose_name_plural = "Sidecar环境变量"
        unique_together = ('key', 'cloud_region')
