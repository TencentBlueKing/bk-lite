# -- coding: utf-8 --
# @File: collect_model.py
# @Time: 2025/2/27 14:04
# @Author: windyzhao

from django.db import models
from django.db.models import JSONField
from apps.core.models.time_info import TimeInfo
from apps.core.models.maintainer_info import MaintainerInfo
from apps.cmdb.constants.constants import CollectPluginTypes, CollectDriverTypes, CollectRunStatusType, CollectInputMethod


class CollectModels(MaintainerInfo, TimeInfo):
    """
    专业采集-协议-云-vm-snmp-k8s
    """

    name = models.CharField(max_length=128, help_text="任务名称")
    task_type = models.CharField(max_length=32, choices=CollectPluginTypes.CHOICE, help_text="任务类型")
    driver_type = models.CharField(max_length=32, choices=CollectDriverTypes.CHOICE,
                                   default=CollectDriverTypes.PROTOCOL, help_text="驱动类型")
    model_id = models.CharField(max_length=64, help_text="模型ID")

    is_interval = models.BooleanField(default=False, help_text="是否开启周期巡检")
    cycle_value_type = models.CharField(max_length=32, help_text="周期任务类型")
    cycle_value = models.CharField(max_length=32, blank=True, null=True, help_text="周期任务值")
    scan_cycle = models.CharField(max_length=50, blank=True, null=True, help_text="扫描周期")

    ip_range = models.TextField(blank=True, null=True, help_text="IP范围")
    instances = JSONField(default=list, help_text="实例")

    access_point = JSONField(default=dict, help_text="接入点")
    credential = JSONField(default=list, help_text="凭据")

    timeout = models.PositiveSmallIntegerField(default=0, help_text="超时时间(单个ip)")

    exec_status = models.PositiveSmallIntegerField(
        default=CollectRunStatusType.NOT_START, choices=CollectRunStatusType.CHOICE, help_text="执行状态"
    )
    exec_time = models.DateTimeField(blank=True, null=True, help_text="执行时间")

    task_id = models.CharField(max_length=64, blank=True, null=True, help_text="任务执行id")

    params = JSONField(default=dict, help_text="采集任务额外的参数(各种实例或者不包括在凭据里的参数)")

    plugin_id = models.IntegerField(default=0, help_text="采集插件ID")

    # 审批
    input_method = models.PositiveSmallIntegerField(
        default=CollectInputMethod.AUTO, choices=CollectInputMethod.CHOICE, help_text="录入方式"
    )
    examine = models.BooleanField(default=False, help_text="是否已经审批")

    collect_data = JSONField(default=dict, help_text="采集原数据")
    collect_digest = JSONField(default=dict, help_text="采集摘要数据")
    format_data = JSONField(default=dict, help_text="采集返回的分类后的数据")

    class Meta:
        verbose_name = "采集任务"
        unique_together = ("name", "driver_type", "model_id")

    @property
    def info(self):
        # 详情
        add_data = self.format_data.get("add", [])
        update_data = self.format_data.get("update", [])
        delete_data = self.format_data.get("delete", [])
        relation_data = self.format_data.get("association", [])

        return {
            "add": {"data": add_data, "count": len(add_data)},
            "update": {"data": update_data, "count": len(update_data)},
            "delete": {"data": delete_data, "count": len(delete_data)},
            "relation": {"data": relation_data, "count": len(relation_data)},
        }

    @property
    def is_k8s(self):
        return self.task_type == CollectPluginTypes.K8S

    @property
    def is_network_topo(self):
        return self.model_id == "network_topo"

    @property
    def is_cloud(self):
        return self.task_type == CollectPluginTypes.CLOUD

    @property
    def is_job(self):
        return self.driver_type == CollectDriverTypes.JOB

    @property
    def is_host(self):
        return self.task_type == CollectPluginTypes.HOST

    @property
    def is_db(self):
        return self.task_type == CollectPluginTypes.DB


class OidMapping(MaintainerInfo, TimeInfo):
    """
    oid库映射表
    """

    model = models.CharField(max_length=128, null=True, verbose_name="设备型号")
    oid = models.CharField(max_length=64, unique=True, help_text="设备oid")
    brand = models.CharField(max_length=64, null=True, help_text="品牌")
    device_type = models.CharField(max_length=128, help_text="设备类型")
    built_in = models.BooleanField(default=False, verbose_name="是否内置")
