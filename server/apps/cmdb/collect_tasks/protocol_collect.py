# -- coding: utf-8 --
# @File: protocol_collect.py
# @Time: 2025/11/12 14:40
# @Author: windyzhao
from apps.cmdb.collect_tasks.aliyun import AliyunCollect
from apps.cmdb.collect_tasks.aws import AWSCollect
from apps.cmdb.collect_tasks.k8s import K8sCollect
from apps.cmdb.collect_tasks.network import NetworkCollect
from apps.cmdb.collect_tasks.protocol import ProtocolTaskCollect
from apps.cmdb.collect_tasks.qcloud import QCloudCollect
from apps.cmdb.collect_tasks.vmware import VmwareCollect
from apps.cmdb.constants.constants import CollectPluginTypes


class ProtocolCollect(object):
    def __init__(self, task, default_metrics=None):
        self.task = task
        self.default_metrics = default_metrics

    @property
    def collect_cloud_manage(self):
        data = {
            "aliyun_account": self.collect_aliyun,
            "qcloud": self.collect_qcloud,
            "aws": self.collect_aws,
        }
        return data

    @property
    def collect_manage(self):
        result = {
            CollectPluginTypes.VM: self.collect_vmware,
            CollectPluginTypes.SNMP: self.collect_network,
            CollectPluginTypes.K8S: self.collect_k8s,
            CollectPluginTypes.PROTOCOL: self.collect_protocol
        }
        result.update(self.collect_cloud_manage)
        return result

    def get_instance(self):
        instance = self.task.instances[0] if self.task.instances else None
        return instance

    def format_params(self):
        pass

    def collect_k8s(self):
        data = K8sCollect(self.task.id)()
        return data

    def collect_vmware(self):
        data = VmwareCollect(self.task.id, self.default_metrics)()
        return data

    def collect_network(self):
        data = NetworkCollect(self.task.id)()
        return data

    def collect_protocol(self):
        data = ProtocolTaskCollect(self.task.id)()
        return data

    def collect_aliyun(self):
        data = AliyunCollect(self.task.id)()
        return data

    def collect_qcloud(self):
        return QCloudCollect(self.task.id)()

    def collect_aws(self):
        return AWSCollect(self.task.id)()

    def main(self):
        if self.task.is_cloud:
            return self.collect_cloud_manage[self.task.model_id]()
        return self.collect_manage[self.task.task_type]()
