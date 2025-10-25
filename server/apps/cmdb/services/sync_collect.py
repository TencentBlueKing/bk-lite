# -- coding: utf-8 --
# @File: sync_collect.py
# @Time: 2025/3/4 10:31
# @Author: windyzhao
from apps.cmdb.constants import CollectPluginTypes
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.collection.service import MetricsCannula, CollectK8sMetrics, CollectVmwareMetrics, \
    CollectNetworkMetrics, ProtocolCollectMetrics, AliyunCollectMetrics, HostCollectMetrics, \
    MiddlewareCollectMetrics, QCloudCollectMetrics, DBCollectCollectMetrics, AWSCollectMetrics


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


class BaseCollect(object):
    COLLECT_PLUGIN = None

    def __init__(self, instance_id, default_metrics=None):
        self.task = CollectModels.objects.get(id=instance_id)
        self.default_metrics = default_metrics
        self.model_id, self.inst_name, self.organization, self.inst_id, self.filter_collect_task = self.format_params()

    def format_params(self):
        if not self.task.instances:
            return self.task.model_id, None, None, self.get_organization, None

        instance = self.task.instances[0]
        model_id = instance["model_id"]
        inst_name = instance["inst_name"]
        organization = instance["organization"]
        inst_id = instance["_id"]
        return model_id, inst_name, organization, inst_id, not self.task.is_host

    @property
    def get_organization(self):
        return self.task.params["organization"]

    @property
    def task_id(self):
        if self.task.is_k8s:
            return self.inst_name
        return self.task.id

    def run(self):
        if self.COLLECT_PLUGIN is None:
            raise NotImplementedError("Please implement the collect plugin")

        metrics_cannula = MetricsCannula(inst_id=self.inst_id, organization=self.organization, inst_name=self.inst_name,
                                         task_id=self.task_id, collect_plugin=self.COLLECT_PLUGIN,
                                         manual=self.task.input_method, default_metrics=self.default_metrics,
                                         filter_collect_task=self.filter_collect_task)

        result = metrics_cannula.collect_controller()
        format_data = self.format_collect_data(result)

        return metrics_cannula.collect_data, format_data

    def format_collect_data(self, result):
        format_data = {"add": [], "update": [], "delete": [], "association": []}
        for value in result.values():
            for operator, datas in value.items():
                for status, data in datas.items():
                    for i in data:

                        assos_result = i.pop("assos_result", {})
                        format_assos_result = self.format_assos_result(assos_result)
                        if format_assos_result:
                            format_data["association"].extend(format_assos_result)

                        _data = {"_status": status}
                        if status == "failed":
                            update_data = i.get("instance_info")
                        else:
                            update_data = i.get("inst_info")
                        if not update_data:
                            continue
                        _data.update(update_data)
                        format_data[operator].append(_data)

        return format_data

    @staticmethod
    def format_assos_result(assos_result):
        result = []
        for status, data in assos_result.items():
            for i in data:
                i["_status"] = status
                result.append(i)
        return result

    def __call__(self, *args, **kwargs):
        return self.run()


class K8sCollect(BaseCollect):
    COLLECT_PLUGIN = CollectK8sMetrics


class VmwareCollect(BaseCollect):
    COLLECT_PLUGIN = CollectVmwareMetrics


class NetworkCollect(BaseCollect):
    COLLECT_PLUGIN = CollectNetworkMetrics


class ProtocolTaskCollect(BaseCollect):
    COLLECT_PLUGIN = ProtocolCollectMetrics


class AliyunCollect(BaseCollect):
    COLLECT_PLUGIN = AliyunCollectMetrics

class QCloudCollect(BaseCollect):
    COLLECT_PLUGIN = QCloudCollectMetrics

class AWSCollect(BaseCollect):
    COLLECT_PLUGIN = AWSCollectMetrics
# ======


class JobCollect(object):
    def __init__(self, task, default_metrics=None):
        self.task = task
        self.default_metrics = default_metrics

    @property
    def collect_manage(self):
        result = {
            CollectPluginTypes.HOST: self.collect_host,
            CollectPluginTypes.DB: self.collect_db,
            CollectPluginTypes.MIDDLEWARE: self.collect_middleware
        }
        return result

    def get_instance(self):
        instance = self.task.instances[0] if self.task.instances else None
        return instance

    def collect_host(self):
        data = HostCollect(self.task.id)()
        return data

    def collect_middleware(self):
        data = MiddlewareCollect(self.task.id)()
        return data

    def collect_db(self):
        return DBCollect(self.task.id)()

    def main(self):
        return self.collect_manage[self.task.task_type]()


class HostCollect(BaseCollect):
    COLLECT_PLUGIN = HostCollectMetrics

class MiddlewareCollect(BaseCollect):
    COLLECT_PLUGIN = MiddlewareCollectMetrics

class DBCollect(BaseCollect):
    COLLECT_PLUGIN = DBCollectCollectMetrics