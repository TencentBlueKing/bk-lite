from django.db import models, transaction
from django.db.models.expressions import BaseExpression
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
        indexes = [
            models.Index(fields=["type", "status"], name="nm_ctrl_task_type_st_idx"),
        ]


class ControllerTaskNodeQuerySet(models.QuerySet):
    def update(self, **kwargs):
        if "organizations" in kwargs:
            if isinstance(kwargs["organizations"], BaseExpression):
                raise ValueError("organizations 表达式更新无法安全规范化")
            kwargs["organizations"] = ControllerTaskNode.normalized_organizations(kwargs["organizations"])
        return super().update(**kwargs)

    def bulk_create(self, objs, *args, **kwargs):
        objs = list(objs)
        for obj in objs:
            obj.normalize_organizations_snapshot()
        return super().bulk_create(objs, *args, **kwargs)

    def bulk_update(self, objs, fields, *args, **kwargs):
        objs = list(objs)
        if "organizations" in fields:
            for obj in objs:
                obj.normalize_organizations_snapshot()
            with transaction.atomic(using=self.db):
                for obj in objs:
                    obj.save(update_fields=fields, using=self.db)
            return len(objs)
        return super().bulk_update(objs, fields, *args, **kwargs)


class ControllerTaskNode(models.Model):
    task = models.ForeignKey(ControllerTask, on_delete=models.CASCADE, verbose_name="任务")
    node_id = models.CharField(max_length=100, blank=True, default="", db_index=True, verbose_name="节点ID")
    ip = models.CharField(max_length=100, verbose_name="IP地址")
    node_name = models.CharField(max_length=200, default="", verbose_name="节点名称")
    os = models.CharField(max_length=100, verbose_name="操作系统")
    cpu_architecture = models.CharField(max_length=20, blank=True, default="", verbose_name="CPU架构")
    organizations = JSONField(default=list, verbose_name="所属组织")
    port = models.IntegerField(verbose_name="端口")
    username = models.CharField(max_length=100, verbose_name="用户名")
    password = models.CharField(max_length=100, verbose_name="密码")
    private_key = models.TextField(default="", blank=True, verbose_name="SSH私钥")
    passphrase = models.TextField(default="", blank=True, verbose_name="私钥密码短语")
    winrm_scheme = models.CharField(max_length=16, blank=True, default="https", verbose_name="WinRM协议")
    winrm_transport = models.CharField(max_length=32, blank=True, default="ntlm", verbose_name="WinRM认证方式")
    winrm_cert_validation = models.BooleanField(default=True, verbose_name="WinRM证书校验")
    resolved_package_version_id = models.IntegerField(default=0, verbose_name="解析后的控制器版本")
    status = models.CharField(max_length=100, default="", verbose_name="任务状态")
    result = JSONField(default=dict, verbose_name="结果")

    objects = ControllerTaskNodeQuerySet.as_manager()

    class Meta:
        verbose_name = "控制器任务节点"
        verbose_name_plural = "控制器任务节点"
        indexes = [
            models.Index(fields=["ip", "status"], name="nm_ctrl_node_ip_st_idx"),
            models.Index(fields=["task", "status"], name="nm_ctrl_tasknode_st_idx"),
        ]

    def normalize_organizations_snapshot(self):
        self.organizations = self.normalized_organizations(self.organizations)

    @staticmethod
    def normalized_organizations(organizations):
        if not isinstance(organizations, list) or any(isinstance(value, bool) or not isinstance(value, int) for value in organizations):
            # 非规范历史快照必须 fail closed；提前清空可避免 MySQL JSON 将 1.0
            # 反序列化为 1 后意外获得组织权限。
            return []
        return organizations

    def save(self, *args, **kwargs):
        self.normalize_organizations_snapshot()
        return super().save(*args, **kwargs)


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
