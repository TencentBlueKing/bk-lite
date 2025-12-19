from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.node_mgmt.models.sidecar import Node


class NodeComponentVersion(TimeInfo, MaintainerInfo):
    """节点组件版本信息"""

    node = models.ForeignKey(Node, on_delete=models.CASCADE, verbose_name="节点", related_name="component_versions")
    component_type = models.CharField(max_length=50, verbose_name="组件类型(控制器和采集器)")
    component_id = models.CharField(max_length=100, verbose_name="组件ID")
    version = models.CharField(max_length=100, verbose_name="版本号")
    latest_version = models.CharField(max_length=100, blank=True, default="", verbose_name="最新版本号")
    upgradeable = models.BooleanField(default=False, verbose_name="是否可升级")
    message = models.TextField(blank=True, default="", verbose_name="执行信息")
    last_check_at = models.DateTimeField(auto_now=True, verbose_name="最后检查时间")

    class Meta:
        verbose_name = "节点组件版本信息"
        verbose_name_plural = "节点组件版本信息"
        unique_together = ('node', 'component_type', 'component_id')
