from django.db import models
from django.db.models import JSONField

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.node_mgmt.models import CloudRegion, Node, Collector


class NodeCollectorInstallStatus(models.Model):
    node = models.ForeignKey(Node, on_delete=models.CASCADE, verbose_name="节点")
    collector = models.ForeignKey(Collector, on_delete=models.CASCADE, verbose_name="采集器")
    status = models.CharField(max_length=100, verbose_name="状态")
    result = JSONField(default=dict, verbose_name="结果")

    class Meta:
        verbose_name = "节点采集器状态"
        verbose_name_plural = "节点采集器状态"


class ControllerTask(TimeInfo, MaintainerInfo):

    cloud_region = models.ForeignKey(CloudRegion, on_delete=models.CASCADE, verbose_name="云区域")
    type = models.CharField(max_length=100, verbose_name="任务类型")
    status = models.CharField(max_length=100, verbose_name="任务状态")
    work_node = models.CharField(max_length=100, blank=True, verbose_name="工作节点")
    package_version_id = models.IntegerField(default=0, verbose_name="控制器版本")

    class Meta:
        verbose_name = "控制器任务"
        verbose_name_plural = "控制器任务"


class ControllerTaskNode(models.Model):

    task = models.ForeignKey(ControllerTask, on_delete=models.CASCADE, verbose_name="任务")
    ip = models.CharField(max_length=100, verbose_name="IP地址")
    node_name = models.CharField(max_length=200, default="", verbose_name="节点名称")
    os = models.CharField(max_length=100, verbose_name="操作系统")
    organizations = JSONField(default=list, verbose_name="所属组织")
    port = models.IntegerField(verbose_name="端口")
    username = models.CharField(max_length=100, verbose_name="用户名")
    password = models.CharField(max_length=100, verbose_name="密码")
    private_key = models.TextField(default="", blank=True, verbose_name="SSH私钥")
    passphrase = models.TextField(default="", blank=True, verbose_name="私钥密码短语")
    status = models.CharField(max_length=100, default="", verbose_name="任务状态")
    result = JSONField(default=dict, verbose_name="结果")

    class Meta:
        verbose_name = "控制器任务节点"
        verbose_name_plural = "控制器任务节点"


class CollectorTask(TimeInfo, MaintainerInfo):

    type = models.CharField(max_length=100, verbose_name="任务类型")
    package_version_id = models.IntegerField(default=0, verbose_name="采集器版本")
    status = models.CharField(max_length=100, verbose_name="任务状态")

    class Meta:
        verbose_name = "采集器任务"
        verbose_name_plural = "采集器任务"


class CollectorTaskNode(models.Model):

    task = models.ForeignKey(CollectorTask, on_delete=models.CASCADE, verbose_name="任务")
    node = models.ForeignKey(Node, on_delete=models.CASCADE, verbose_name="节点")
    status = models.CharField(max_length=100, verbose_name="任务状态")
    result = JSONField(default=dict, verbose_name="结果")

    class Meta:
        verbose_name = "采集器任务节点"
        verbose_name_plural = "采集器任务节点"
