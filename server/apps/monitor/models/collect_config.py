from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.monitor.models.monitor_object import MonitorInstance
from apps.monitor.models.plugin import MonitorPlugin


class CollectConfig(TimeInfo, MaintainerInfo):
    id = models.CharField(primary_key=True, max_length=100, verbose_name="配置ID")
    monitor_instance = models.ForeignKey(MonitorInstance, on_delete=models.CASCADE, verbose_name="监控对象实例")
    monitor_plugin = models.ForeignKey(MonitorPlugin, blank=True, null=True, on_delete=models.CASCADE, verbose_name="监控插件")
    collector = models.CharField(max_length=100, verbose_name="采集器名称")
    collect_type = models.CharField(max_length=50, verbose_name="采集类型")
    config_type = models.CharField(max_length=50, verbose_name="配置类型")
    file_type = models.CharField(max_length=50, verbose_name="文件类型")
    is_child = models.BooleanField(default=True, verbose_name="是否子配置")
    applied_content_sha256 = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        verbose_name="已应用插件内容指纹",
    )
    applied_rendered_sha256 = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="上次模板渲染内容哈希",
    )
    applied_pack_version = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="已应用的探针包版本",
    )
    content_hand_edited = models.BooleanField(default=False, verbose_name="采集配置已被手改")
    vault_credential_id = models.CharField(max_length=128, default="", db_index=True, verbose_name="凭据仓库 ID")
    vault_variant = models.CharField(max_length=32, default="", verbose_name="凭据分支")
    vault_actor_context = models.JSONField(default=dict, verbose_name="凭据绑定人")
    vault_credential_name = models.CharField(max_length=128, default="", verbose_name="凭据名称快照")
    vault_applied_version = models.PositiveIntegerField(default=0, verbose_name="已下发凭据版本")
    vault_sync_error = models.CharField(max_length=32, default="", verbose_name="凭据同步错误码")
    vault_synced_at = models.DateTimeField(null=True, blank=True, verbose_name="凭据下发时间")

    class Meta:
        verbose_name = "采集配置"
        verbose_name_plural = "采集配置"
        unique_together = ("monitor_instance", "collector", "collect_type", "config_type")
