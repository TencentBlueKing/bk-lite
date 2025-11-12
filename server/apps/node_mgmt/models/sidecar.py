import uuid

from django.db import models
from django.db.models import JSONField

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.models.cloud_region import CloudRegion

OS_TYPE = (
    ("linux", "Linux"),
    ("windows", "Windows"),
)


class Controller(TimeInfo, MaintainerInfo):
    os = models.CharField(max_length=50, choices=OS_TYPE, verbose_name="操作系统类型")
    name = models.CharField(max_length=100, verbose_name="控制器名称")
    description = models.TextField(blank=True, verbose_name="控制器描述")

    class Meta:
        verbose_name = "控制器信息"
        verbose_name_plural = "控制器信息"
        unique_together = ('os', 'name')


class Node(TimeInfo, MaintainerInfo):
    id = models.CharField(primary_key=True, max_length=100, verbose_name="节点ID")
    name = models.CharField(max_length=100, verbose_name="节点名称")
    ip = models.CharField(max_length=30, verbose_name="IP地址")
    operating_system = models.CharField(max_length=50, choices=OS_TYPE, verbose_name="操作系统类型")
    collector_configuration_directory = models.CharField(max_length=200, verbose_name="采集器配置目录")
    metrics = JSONField(default=dict, verbose_name="指标")
    status = JSONField(default=dict, verbose_name="状态")
    tags = JSONField(default=list, verbose_name="标签")
    log_file_list = JSONField(default=list, verbose_name="日志文件列表")
    cloud_region = models.ForeignKey(CloudRegion, default=1, on_delete=models.CASCADE, verbose_name="云区域")
    install_method = models.CharField(max_length=50, default=ControllerConstants.AUTO, verbose_name="安装方式")

    class Meta:
        verbose_name = "节点信息"
        verbose_name_plural = "节点信息"


class NodeOrganization(TimeInfo, MaintainerInfo):
    node = models.ForeignKey(Node, on_delete=models.CASCADE, verbose_name="节点")
    organization = models.IntegerField(verbose_name="组织id")

    class Meta:
        verbose_name = "节点组织"
        verbose_name_plural = "节点组织"
        unique_together = ('node', 'organization')


class Collector(TimeInfo, MaintainerInfo):
    ServiceType = (
        ("exec", "执行任务"),
        ("svc", "服务"),
    )

    id = models.CharField(primary_key=True, max_length=100, verbose_name="采集器ID")
    name = models.CharField(max_length=100, verbose_name="采集器名称")
    service_type = models.CharField(max_length=100, choices=ServiceType, verbose_name="服务类型")
    node_operating_system = models.CharField(max_length=50, choices=OS_TYPE, verbose_name="节点操作系统类型")
    executable_path = models.CharField(max_length=200, verbose_name="可执行文件路径")
    execute_parameters = models.CharField(max_length=200, verbose_name="执行参数")
    validation_parameters = models.CharField(blank=True, null=True, max_length=200, verbose_name="验证参数")
    default_template = models.TextField(blank=True, null=True, verbose_name="默认模板")
    introduction = models.TextField(blank=True, verbose_name="采集器介绍")
    icon = models.CharField(max_length=100, default="", verbose_name="图标key")
    controller_default_run = models.BooleanField(default=False, verbose_name="控制器默认运行")
    enabled_default_config = models.BooleanField(default=False, verbose_name="是否启用默认初始化的配置")
    default_config = JSONField(default=dict, verbose_name="默认初始化的配置")
    tags = JSONField(default=list, verbose_name="标签")
    package_name = models.CharField(max_length=100, blank=True, default="", verbose_name="包名称")

    class Meta:
        verbose_name = "采集器信息"
        verbose_name_plural = "采集器信息"
        unique_together = ('node_operating_system', 'name')


class CollectorConfiguration(TimeInfo, MaintainerInfo):
    id = models.CharField(primary_key=True, max_length=100, verbose_name="配置ID")
    name = models.CharField(unique=True, max_length=100, verbose_name="配置名称")
    config_template = models.TextField(blank=True, verbose_name="配置模板")
    collector = models.ForeignKey(Collector, on_delete=models.CASCADE, verbose_name="采集器")
    nodes = models.ManyToManyField(Node, through="NodeCollectorConfiguration", blank=True,verbose_name="节点")
    cloud_region = models.ForeignKey(CloudRegion, default=1, on_delete=models.CASCADE, verbose_name="云区域")
    is_pre = models.BooleanField(default=False, verbose_name="是否预定义")
    env_config = JSONField(default=dict, verbose_name="环境变量配置")

    class Meta:
        verbose_name = "采集器配置信息"
        verbose_name_plural = "采集器配置信息"

    # uuid
    def save(self, *args, **kwargs):
        if not self.id:
            self.id = str(uuid.uuid4().hex)
        super().save(*args, **kwargs)


class NodeCollectorConfiguration(models.Model):
    node = models.ForeignKey("Node", on_delete=models.CASCADE)
    collector_config = models.ForeignKey("CollectorConfiguration", on_delete=models.CASCADE)

    class Meta:
        unique_together = ("node", "collector_config")


class ChildConfig(TimeInfo, MaintainerInfo):
    id = models.CharField(primary_key=True, max_length=100, verbose_name="子配置ID")
    collect_type = models.CharField(max_length=50, verbose_name='采集类型')
    config_type = models.CharField(max_length=50, verbose_name='配置类型')
    content = models.TextField(verbose_name='内容')
    collector_config = models.ForeignKey(CollectorConfiguration, on_delete=models.CASCADE, verbose_name='采集器配置')
    env_config = JSONField(default=dict, verbose_name="环境变量配置")
    sort_order = models.IntegerField(default=0, verbose_name='排序序号')

    class Meta:
        verbose_name = "子配置"
        verbose_name_plural = "子配置"
        ordering = ['sort_order', 'created_at']  # 默认按排序序号排序，次要按创建时间排序

    # uuid
    def save(self, *args, **kwargs):
        if not self.id:
            self.id = str(uuid.uuid4().hex)
        super().save(*args, **kwargs)


class Action(TimeInfo, MaintainerInfo):
    node = models.ForeignKey(Node, on_delete=models.CASCADE, verbose_name="节点")
    action = JSONField(default=list, verbose_name="操作")

    class Meta:
        verbose_name = "操作信息"
        verbose_name_plural = "操作信息"


class SidecarApiToken(TimeInfo, MaintainerInfo):
    node_id = models.CharField(max_length=100, default="", verbose_name="节点ID")
    token = models.CharField(max_length=250, verbose_name="Token")

    class Meta:
        verbose_name = "Sidecar API Token"
        verbose_name_plural = "Sidecar API Token"
